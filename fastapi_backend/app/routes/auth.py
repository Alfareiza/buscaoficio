"""
Authentication routes for Buscaoficio.

All flows (register, login, logout, email verification, password reset) are
documented in docs/auth.md at the repository root. Read that first if you are
new to the project — it explains why these routes exist explicitly instead of
relying on fastapi-users' built-in router, how permissions work, and how to
create a superuser.
"""

import secrets
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi_users import exceptions
from fastapi_users.authentication import Strategy
from fastapi_users.router.common import ErrorCode
from pydantic import EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import logger, settings
from app.database import get_async_session
from app.email import send_otp_code_email
from app.google_oauth_manager import GoogleOAuthError, GoogleOAuthManager
from app.models import Cliente, Profesional, RefreshToken, User
from app.otp_manager import OtpManager
from app.refresh_token_manager import RefreshTokenManager, build_session_response
from app.schemas import (
    ClienteRegisterOtpCreate,
    OtpRequestIn,
    OtpVerifyIn,
    ProfesionalRegisterOtpCreate,
    UserRead,
)
from app.users import UserManager, auth_backend, current_user_token, get_user_manager
from app.utils import get_client_ip

router = APIRouter(tags=["auth"])


def _registration_session_extra(user: User, token_payload: dict) -> dict:
    """Build the extra fields for a just-completed registration's session
    response. `nombre_completo`/`email`/`picture` are only included when the
    registration_token was Google-backed (carries `google_sub`) — same
    "picture present ⇒ Google" signal /google/session uses, so the frontend
    caches a "Welcome back" identity only for Google signups, not OTP ones."""
    extra = {"status": "existing_user", "has_role": True}
    if token_payload.get("google_sub") is not None:
        extra["nombre_completo"] = user.nombre_completo
        extra["email"] = user.email
        extra["picture"] = token_payload.get("picture")
    return extra


async def _user_has_role(db: AsyncSession, user_id: UUID) -> bool:
    """Whether `user_id` already has a cliente or profesional profile.
    Shared by every route that logs an existing user in (OTP verify, Google
    Sign-In) so the `has_role` computation exists in exactly one place."""
    cliente_row = await db.execute(
        select(Cliente.usuario_id).where(Cliente.usuario_id == user_id)
    )
    profesional_row = await db.execute(
        select(Profesional.usuario_id).where(Profesional.usuario_id == user_id)
    )
    return (
        cliente_row.scalar_one_or_none() is not None
        or profesional_row.scalar_one_or_none() is not None
    )


@router.post("/jwt/logout", summary="Logout", name="auth:jwt.logout")
async def logout(
    user_token: tuple[User, str] = Depends(current_user_token),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    """Invalidate all refresh tokens for the user.

    Revokes all active refresh tokens (forcing re-login on all devices).
    Also clears the refresh and fingerprint cookies.
    """
    user, token = user_token
    await RefreshTokenManager.revoke_all_user_tokens(db, user.id)

    response = await auth_backend.logout(strategy, user, token)

    response.delete_cookie(
        "refreshToken", path="/api/v1/auth/jwt/refresh", secure=True, httponly=True
    )
    response.delete_cookie(
        "fingerprintToken", path="/api/v1/auth/jwt/refresh", secure=True, httponly=True
    )

    logger.info(f"User {user} logged out, all sessions revoked")
    return response


@router.post(
    "/otp/request",
    summary="Request a passwordless login code",
    status_code=status.HTTP_202_ACCEPTED,
    name="auth:otp.request",
)
async def otp_request(
    request: Request,
    payload: OtpRequestIn,
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """Send a 6-digit code to `email`, valid for OTP_CODE_EXPIRE_SECONDS.

    Works identically whether the email belongs to an existing user or not —
    account creation happens later, in POST /auth/register/{cliente,
    profesional}/otp, after the code is verified. Always responds 202
    regardless of outcome (anti-enumeration, same pattern as
    /auth/forgot-password) — a resend within the cooldown window is silently
    a no-op.
    """
    code = await OtpManager.request_code(db, payload.email, get_client_ip(request))
    if code is not None:
        await send_otp_code_email(payload.email, code)
    return None


@router.post(
    "/otp/verify",
    summary="Verify a passwordless login code",
    name="auth:otp.verify",
)
async def otp_verify(
    request: Request,
    payload: OtpVerifyIn,
    user_manager: UserManager = Depends(get_user_manager),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
    db: AsyncSession = Depends(get_async_session),
):
    """Verify a code requested via POST /auth/otp/request.

    If `email` already has an account, logs it in (access token +
    refresh/fingerprint cookies, via build_session_response). Otherwise
    returns a short-lived registration_token proving the email was verified,
    to be used with POST /auth/register/cliente/otp or POST
    /auth/register/profesional/otp.
    """
    valid = await OtpManager.verify_code(db, payload.email, payload.code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o expirado",
        )

    user = await user_manager.user_db.get_by_email(payload.email)
    if user is None:
        registration_token = OtpManager.issue_registration_token(payload.email)
        return {"status": "new_user", "registration_token": registration_token}

    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
        )

    has_role = await _user_has_role(db, user.id)
    response = await build_session_response(
        user,
        strategy,
        db,
        request,
        extra={"status": "existing_user", "has_role": has_role},
    )
    await user_manager.on_after_login(user, request, response)
    logger.info(f"User {user.id} logged in via OTP from {get_client_ip(request)}")
    return response


@router.get(
    "/google/authorize",
    summary="Start Google Sign-In",
    name="auth:google.authorize",
)
async def google_authorize() -> RedirectResponse:
    """Redirect the browser to Google's consent screen.

    This is a real browser navigation (the "Continuar con Google" button is
    a plain link, not a fetch call) — the whole Authorization Code flow
    depends on the browser bouncing through Google, so it can't go through a
    Next.js Server Action the way every other auth call in this app does.
    """
    if not GoogleOAuthManager.is_configured():
        logger.warning(
            "Google Sign-In attempted but not configured "
            "(missing GOOGLE_OAUTH_CLIENT_ID/GOOGLE_OAUTH_CLIENT_SECRET)"
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google Sign-In is not configured",
        )
    state = GoogleOAuthManager.issue_state()
    url = await GoogleOAuthManager.get_authorization_url(state)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/google/callback",
    summary="Google Sign-In callback",
    name="auth:google.callback",
)
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    user_manager: UserManager = Depends(get_user_manager),
    db: AsyncSession = Depends(get_async_session),
) -> RedirectResponse:
    """Google redirects here after the user accepts/rejects consent.

    This route only ever redirects the browser onward — it never sets
    session cookies itself, since those must be set by the Next.js server on
    its own origin (see GoogleOAuthManager.issue_session_token's docstring).
    Existing users get a short-lived google_session_token to complete login
    via POST /auth/google/session; new emails get the same registration_token
    the OTP flow already uses, so /register/{cliente,profesional}/otp handles
    account creation identically regardless of how the email was proven.
    """
    login_url = f"{settings.FRONTEND_URL}/login"

    if error is not None or code is None or state is None:
        logger.warning(f"Google Sign-In cancelled or malformed callback: error={error}")
        return RedirectResponse(f"{login_url}?error=google_auth_failed")

    if not GoogleOAuthManager.is_configured() or not GoogleOAuthManager.verify_state(
        state
    ):
        logger.warning("Google Sign-In callback with invalid/expired state")
        return RedirectResponse(f"{login_url}?error=google_auth_failed")

    try:
        profile = await GoogleOAuthManager.exchange_code_for_profile(code)
    except GoogleOAuthError:
        logger.warning("Google Sign-In code exchange failed")
        return RedirectResponse(f"{login_url}?error=google_auth_failed")

    if not profile.email_verified:
        logger.warning("Google Sign-In rejected: unverified email")
        return RedirectResponse(f"{login_url}?error=google_auth_failed")

    user_result = await db.execute(select(User).where(User.google_sub == profile.sub))
    user = user_result.scalar_one_or_none()

    if user is None:
        user = await user_manager.user_db.get_by_email(profile.email)
        if user is not None and user.google_sub is None and user.deleted_at is None:
            # Existing account (created via OTP) signing in with Google for
            # the first time — link by verified email, matching how this
            # app already treats email as the canonical identity.
            user.google_sub = profile.sub
            db.add(user)
            try:
                await db.commit()
                await db.refresh(user)
            except IntegrityError:
                # Two concurrent callbacks for the same not-yet-linked email
                # (e.g. a duplicated/retried navigation to this route) can
                # both pass the `google_sub is None` check above and race to
                # commit. The loser hits the unique constraint on
                # google_sub — reload rather than 500ing, since the row is
                # now linked exactly the way this request wanted anyway.
                await db.rollback()
                user = await user_manager.user_db.get_by_email(profile.email)

    if user is None:
        registration_token = OtpManager.issue_registration_token(
            profile.email,
            google_sub=profile.sub,
            nombre_completo=profile.name,
            picture=profile.picture,
        )
        register_url = f"{settings.FRONTEND_URL}/register"
        params = f"registration_token={registration_token}&provider=google"
        if profile.name:
            params += f"&name={quote(profile.name)}"
        return RedirectResponse(f"{register_url}?{params}")

    if not user.is_active or user.deleted_at is not None:
        logger.warning(f"Google Sign-In rejected: user {user.id} is inactive")
        return RedirectResponse(f"{login_url}?error=google_auth_failed")

    session_token = GoogleOAuthManager.issue_session_token(
        user.id, picture=profile.picture
    )
    logger.info(
        f"User {user} authenticated via Google from {get_client_ip(request)}"
    )
    # Hands off to a Next.js Route Handler (not a page) so the session is
    # established server-side and the browser lands straight on /dashboard —
    # no intermediate screen between Google's consent flow and the app.
    complete_url = f"{settings.FRONTEND_URL}/api/auth/google/complete"
    return RedirectResponse(f"{complete_url}?google_session_token={session_token}")


@router.post(
    "/google/session",
    summary="Complete Google Sign-In (exchange session token for a session)",
    name="auth:google.session",
)
async def google_session(
    request: Request,
    google_session_token: str = Body(..., embed=True),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
    db: AsyncSession = Depends(get_async_session),
):
    """Called by a Next.js Server Action, not directly by the browser.

    Exchanges the short-lived token from GET /auth/google/callback's
    redirect for a real session (access token + refresh/fingerprint
    cookies), via the same build_session_response used by OTP verify and
    OTP-backed registration — so cookie-setting logic still exists in
    exactly one place. The response also carries `nombre_completo`/`email`/
    `picture` (unlike OTP verify, which doesn't need to — the frontend
    already has the email from what the user typed there) so the frontend
    can cache them for the "Welcome back" card show after a future session
    expiry. `picture` is only ever included for a Google-established
    session — its presence in the response is the frontend's signal that
    this login was Google-backed.
    """
    payload = GoogleOAuthManager.verify_session_token(google_session_token)
    if payload is None or "user_id" not in payload or "jti" not in payload:
        logger.warning(
            "Google session exchange failed: invalid/expired google_session_token"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="google_session_token inválido o expirado",
        )

    if not await GoogleOAuthManager.consume_session_token_jti(db, payload["jti"]):
        # Valid signature, but this exact token already established a
        # session once — reject the replay rather than minting another one.
        logger.warning(
            f"Google session token replay detected: user_id={payload['user_id']}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="google_session_token inválido o expirado",
        )

    user = await user_manager.get(UUID(payload["user_id"]))
    if user is None or not user.is_active or user.deleted_at is not None:
        logger.warning(
            f"Google session exchange failed: user {payload['user_id']} "
            "not found or inactive"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
        )

    has_role = await _user_has_role(db, user.id)
    response = await build_session_response(
        user,
        strategy,
        db,
        request,
        extra={
            "status": "existing_user",
            "has_role": has_role,
            "nombre_completo": user.nombre_completo,
            "email": user.email,
            "picture": payload.get("picture"),
        },
    )
    await user_manager.on_after_login(user, request, response)
    logger.info(
        f"User {user} session established via Google from {get_client_ip(request)}"
    )
    return response


@router.post("/jwt/refresh", summary="Refresh Access Token", name="auth:jwt.refresh")
async def refresh(
    request: Request,
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
) -> JSONResponse:
    """Rotate refresh token and issue new access token.

    Validates the refresh token + fingerprint cookie, then:
    1. Revokes the old refresh token
    2. Issues a new access token
    3. Sets new refresh + fingerprint tokens as cookies

    If an old token is reused (possible theft), revokes all user sessions.

    Returns:
        JSON response with new access_token, token_type, and expires_in.

    Raises:
        401: If refresh token is invalid, expired, or fingerprint mismatch.
    """
    refresh_token_raw = request.cookies.get("refreshToken")
    fingerprint_token_raw = request.cookies.get("fingerprintToken")

    if not refresh_token_raw or not fingerprint_token_raw:
        logger.warning("Refresh attempt missing cookies")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh credentials",
        )

    refresh_hash = RefreshTokenManager._hash_token(refresh_token_raw)
    fingerprint_hash = RefreshTokenManager._hash_token(fingerprint_token_raw)

    stmt = select(RefreshToken).where(RefreshToken.refresh_token_hash == refresh_hash)
    result = await db.execute(stmt)
    refresh_token_row = result.scalar_one_or_none()

    if not refresh_token_row:
        logger.warning("Refresh attempt with invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = refresh_token_row.user_id
    existing_token = await RefreshTokenManager.validate_refresh_token(
        db, user_id, refresh_hash, fingerprint_hash
    )

    if not existing_token:
        await RefreshTokenManager.detect_theft_and_revoke(db, user_id)
        logger.warning(f"Possible token theft detected for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await user_manager.get(user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User inactive or deleted",
        )

    new_access_token = await strategy.write_token(user)

    (
        new_refresh_token_raw,
        new_fingerprint_token_raw,
        new_refresh_hash,
        new_fingerprint_hash,
    ) = RefreshTokenManager.generate_tokens()

    client_ip = get_client_ip(request)
    await RefreshTokenManager.rotate_refresh_token(
        db, existing_token, new_refresh_hash, new_fingerprint_hash, client_ip
    )

    response = JSONResponse(
        content={
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        }
    )

    response.set_cookie(
        "refreshToken",
        new_refresh_token_raw,
        max_age=RefreshTokenManager.REFRESH_TOKEN_LIFETIME,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth/jwt/refresh",
    )
    response.set_cookie(
        "fingerprintToken",
        new_fingerprint_token_raw,
        max_age=RefreshTokenManager.REFRESH_TOKEN_LIFETIME,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth/jwt/refresh",
    )

    logger.info(f"User {user} refreshed token from {client_ip}")
    return response


def _resolve_registration_payload(registration_token: str) -> dict:
    """Decode a registration_token issued by either POST /auth/otp/verify
    (email only) or GET /auth/google/callback (email + google_sub +
    optionally nombre_completo)."""
    payload = OtpManager.verify_registration_token(registration_token)
    if payload is None or "email" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="registration_token inválido o expirado",
        )
    return payload


@router.post(
    "/register/cliente/otp",
    summary="Complete passwordless registration as cliente",
    name="register:register_cliente_otp",
)
async def register_cliente_otp(
    request: Request,
    payload: ClienteRegisterOtpCreate,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
):
    """Create a usuario + cliente profile from an OTP-verified email, then
    log the new user in.

    Proof of email ownership is the registration_token from POST
    /auth/otp/verify, not a password. A random, never-disclosed password is
    stored so the account still satisfies the underlying fastapi-users
    schema — it can never actually be used to log in.
    """
    token_payload = _resolve_registration_payload(payload.registration_token)
    email = token_payload["email"]

    if await user_manager.user_db.get_by_email(email) is not None:
        logger.warning("Cliente OTP registration failed: user already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.REGISTER_USER_ALREADY_EXISTS,
        )

    if payload.referido_por_id is not None:
        referido = await db.execute(
            select(Cliente).filter(Cliente.usuario_id == payload.referido_por_id)
        )
        if not referido.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="referido_por_id not found",
            )

    user = User(
        email=email,
        hashed_password=user_manager.password_helper.hash(secrets.token_urlsafe(32)),
        nombre_completo=payload.nombre_completo,
        whatsapp=payload.whatsapp,
        is_verified=True,  # the OTP/Google verification already proved mailbox ownership
        google_sub=token_payload.get("google_sub"),
    )
    try:
        db.add(user)
        await db.flush()

        db.add(
            Cliente(
                usuario_id=user.id,
                direccion_default=payload.direccion_default,
                referido_por_id=payload.referido_por_id,
            )
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(
            f"Cliente OTP registration failed: integrity error email={email}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration conflicts with an existing record",
        )
    await db.refresh(user)

    await user_manager.on_after_register(user, request)
    logger.info(f"Cliente registered via OTP usuario_id={user.id}")

    response = await build_session_response(
        user,
        strategy,
        db,
        request,
        extra=_registration_session_extra(user, token_payload),
    )
    await user_manager.on_after_login(user, request, response)
    return response


@router.post(
    "/register/profesional/otp",
    summary="Complete passwordless registration as profesional",
    name="register:register_profesional_otp",
)
async def register_profesional_otp(
    request: Request,
    payload: ProfesionalRegisterOtpCreate,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
):
    """Create a usuario + profesional profile from an OTP-verified email,
    then log the new user in. See register_cliente_otp for the general
    passwordless-registration pattern (random unusable password, is_verified
    set immediately). Starts as estado_verificacion=pendiente; verification
    review happens out of band.
    """
    token_payload = _resolve_registration_payload(payload.registration_token)
    email = token_payload["email"]

    if await user_manager.user_db.get_by_email(email) is not None:
        logger.warning("Profesional OTP registration failed: user already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.REGISTER_USER_ALREADY_EXISTS,
        )

    dup_doc = await db.execute(
        select(Profesional).filter(
            Profesional.documento_numero == payload.documento_numero
        )
    )
    if dup_doc.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="documento_numero already registered",
        )

    user = User(
        email=email,
        hashed_password=user_manager.password_helper.hash(secrets.token_urlsafe(32)),
        nombre_completo=payload.nombre_completo,
        whatsapp=payload.whatsapp,
        is_verified=True,
        google_sub=token_payload.get("google_sub"),
    )
    try:
        db.add(user)
        await db.flush()

        db.add(
            Profesional(
                usuario_id=user.id,
                documento_tipo=payload.documento_tipo,
                documento_numero=payload.documento_numero,
                anos_experiencia=payload.anos_experiencia,
                foto_perfil_url=payload.foto_perfil_url,
            )
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(
            f"Profesional OTP registration failed: integrity error email={email}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration conflicts with an existing record",
        )
    await db.refresh(user)

    await user_manager.on_after_register(user, request)
    logger.info(f"Profesional registered via OTP usuario_id={user.id}")

    response = await build_session_response(
        user,
        strategy,
        db,
        request,
        extra=_registration_session_extra(user, token_payload),
    )
    await user_manager.on_after_login(user, request, response)
    return response


@router.post(
    "/forgot-password",
    summary="Start reset (sends email)",
    status_code=status.HTTP_202_ACCEPTED,
    name="reset:forgot_password",
)
async def forgot_password(
    request: Request,
    email: EmailStr = Body(..., embed=True),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Start reset and send email.

    Complete with POST /auth/reset-password. Note: there is no password-based
    sign-in route anymore (see docs/auth.md) — these routes are unlinked in
    the frontend and kept only for password-based accounts, if any exist.
    """
    try:
        user = await user_manager.get_by_email(email)
    except exceptions.UserNotExists:
        logger.info("Password reset requested for unknown email")
        return None

    try:
        await user_manager.forgot_password(user, request)
        logger.info(f"Password reset requested user_id={user.id}")
    except exceptions.UserInactive:
        logger.info(f"Password reset skipped for inactive user_id={user.id}")

    return None


@router.post(
    "/reset-password",
    summary="Complete reset with token",
    name="reset:reset_password",
)
async def reset_password(
    request: Request,
    token: str = Body(...),
    password: str = Body(...),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Complete reset with the emailed token.

    Start with POST /auth/forgot-password.
    """
    try:
        await user_manager.reset_password(token, password, request)
        logger.info("Password reset completed")
    except (
        exceptions.InvalidResetPasswordToken,
        exceptions.UserNotExists,
        exceptions.UserInactive,
    ):
        logger.warning("Password reset failed: bad token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.RESET_PASSWORD_BAD_TOKEN,
        )
    except exceptions.InvalidPasswordException as exc:
        logger.warning("Password reset failed: invalid password")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.RESET_PASSWORD_INVALID_PASSWORD,
                "reason": exc.reason,
            },
        )


@router.post(
    "/request-verify-token",
    summary="Request verification email",
    status_code=status.HTTP_202_ACCEPTED,
    name="verify:request-token",
)
async def request_verify_token(
    request: Request,
    email: EmailStr = Body(..., embed=True),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Request verification email.

    Then POST /auth/verify.
    """
    try:
        user = await user_manager.get_by_email(email)
        await user_manager.request_verify(user, request)
        logger.info(f"Verification token requested user_id={user.id}")
    except (
        exceptions.UserNotExists,
        exceptions.UserInactive,
        exceptions.UserAlreadyVerified,
    ):
        logger.info("Verification token request skipped")

    return None


@router.post(
    "/verify",
    summary="Verify email with token",
    response_model=UserRead,
    name="verify:verify",
)
async def verify(
    request: Request,
    token: str = Body(..., embed=True),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Verify email with token.

    Request it with POST /auth/request-verify-token.
    """
    try:
        user = await user_manager.verify(token, request)
        logger.info(f"User {user.id} verified email")
        return user
    except (exceptions.InvalidVerifyToken, exceptions.UserNotExists):
        logger.warning("Email verification failed: bad token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.VERIFY_USER_BAD_TOKEN,
        )
    except exceptions.UserAlreadyVerified:
        logger.warning("Email verification failed: already verified")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.VERIFY_USER_ALREADY_VERIFIED,
        )
