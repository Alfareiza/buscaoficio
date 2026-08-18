"""
Authentication routes for Buscaoficio.

All flows (register, login, logout, email verification, password reset) are
documented in docs/auth.md at the repository root. Read that first if you are
new to the project — it explains why these routes exist explicitly instead of
relying on fastapi-users' built-in router, how permissions work, and how to
create a superuser.
"""

import secrets
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
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

    logger.info(f"User {user.id} logged out, all sessions revoked")
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

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
        )

    cliente_row = await db.execute(
        select(Cliente.usuario_id).where(Cliente.usuario_id == user.id)
    )
    profesional_row = await db.execute(
        select(Profesional.usuario_id).where(Profesional.usuario_id == user.id)
    )
    has_role = (
        cliente_row.scalar_one_or_none() is not None
        or profesional_row.scalar_one_or_none() is not None
    )
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
    if not user or not user.is_active:
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

    logger.info(f"User {user.id} refreshed token from {client_ip}")
    return response


def _resolve_registration_email(registration_token: str) -> str:
    email = OtpManager.verify_registration_token(registration_token)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="registration_token inválido o expirado",
        )
    return email


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
    email = _resolve_registration_email(payload.registration_token)

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
        is_verified=True,  # the OTP already proved mailbox ownership
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
        user, strategy, db, request, extra={"status": "existing_user", "has_role": True}
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
    email = _resolve_registration_email(payload.registration_token)

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
        user, strategy, db, request, extra={"status": "existing_user", "has_role": True}
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
