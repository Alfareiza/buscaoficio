"""
Authentication routes for Buscaoficio.

All flows (register, login, logout, email verification, password reset) are
documented in docs/auth.md at the repository root. Read that first if you are
new to the project — it explains why these routes exist explicitly instead of
relying on fastapi-users' built-in router, how permissions work, and how to
create a superuser.
"""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions
from fastapi_users.authentication import Strategy
from fastapi_users.router.common import ErrorCode
from pydantic import EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import logger, settings
from app.database import get_async_session
from app.models import Cliente, Profesional, RefreshToken, User
from app.refresh_token_manager import RefreshTokenManager
from app.schemas import (
    ClienteRegisterCreate,
    ProfesionalRegisterCreate,
    UserCreate,
    UserRead,
)
from app.users import UserManager, auth_backend, current_user_token, get_user_manager
from app.utils import get_client_ip

router = APIRouter(tags=["auth"])


@router.post("/jwt/login", summary="Login → JWT", name="auth:jwt.login")
async def login(
    request: Request,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
    db: AsyncSession = Depends(get_async_session),
) -> JSONResponse:
    """Authenticate user and return access token + set refresh token cookie.

    Generates a short-lived access token (returned in response body) and a
    long-lived refresh token (set as HttpOnly cookie). Also sets a
    fingerprint cookie for CSRF/XSS protection.

    Returns:
        JSON response with access_token, token_type, and expires_in.
    """
    user = await user_manager.authenticate(credentials)

    if user is None or not user.is_active:
        logger.warning(f"Login failed for username={credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
        )

    client_ip = get_client_ip(request)

    access_token = await strategy.write_token(user)
    (
        refresh_token_raw,
        fingerprint_token_raw,
        refresh_hash,
        fingerprint_hash,
    ) = RefreshTokenManager.generate_tokens()
    await RefreshTokenManager.store_refresh_token(
        db, user.id, refresh_hash, fingerprint_hash, client_ip
    )
    await db.commit()

    response = JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        }
    )
    response.set_cookie(
        "refreshToken",
        refresh_token_raw,
        max_age=RefreshTokenManager.REFRESH_TOKEN_LIFETIME,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth/jwt/refresh",
    )
    response.set_cookie(
        "fingerprintToken",
        fingerprint_token_raw,
        max_age=RefreshTokenManager.REFRESH_TOKEN_LIFETIME,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth/jwt/refresh",
    )

    await user_manager.on_after_login(user, request, response)
    logger.info(f"User {user.id} logged in from {client_ip}")
    return response


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


@router.post(
    "/register",
    summary="Create user",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    name="register:register",
)
async def register(
    request: Request,
    user_create: UserCreate,
    user_manager: UserManager = Depends(get_user_manager),
):
    """Create user.

    Next: POST /auth/request-verify-token, POST /auth/verify, then
    POST /auth/jwt/login.
    """
    try:
        user = await user_manager.create(user_create, safe=True, request=request)
        return user
    except exceptions.UserAlreadyExists:
        logger.warning("Registration failed: user already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.REGISTER_USER_ALREADY_EXISTS,
        )
    except exceptions.InvalidPasswordException as exc:
        logger.warning("Registration failed: invalid password")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.REGISTER_INVALID_PASSWORD,
                "reason": exc.reason,
            },
        )


@router.post(
    "/register/cliente",
    summary="Register as cliente",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    name="register:register_cliente",
)
async def register_cliente(
    request: Request,
    payload: ClienteRegisterCreate,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Create a usuario and its cliente profile in one request.

    Combines POST /auth/register + POST /users/me/cliente. Next:
    POST /auth/request-verify-token, POST /auth/verify, then
    POST /auth/jwt/login.
    """
    try:
        await user_manager.validate_password(payload.password, payload)
    except exceptions.InvalidPasswordException as exc:
        logger.warning("Cliente registration failed: invalid password")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.REGISTER_INVALID_PASSWORD,
                "reason": exc.reason,
            },
        )

    if await user_manager.user_db.get_by_email(payload.email) is not None:
        logger.warning("Cliente registration failed: user already exists")
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
        email=payload.email,
        hashed_password=user_manager.password_helper.hash(payload.password),
        nombre_completo=payload.nombre_completo,
        whatsapp=payload.whatsapp,
    )
    try:
        db.add(user)
        await db.flush()  # populate user.id without committing

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
            f"Cliente registration failed: integrity error email={payload.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration conflicts with an existing record",
        )
    await db.refresh(user)

    await user_manager.on_after_register(user, request)
    logger.info(f"Cliente registered usuario_id={user.id}")
    return user


@router.post(
    "/register/profesional",
    summary="Register as profesional",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    name="register:register_profesional",
)
async def register_profesional(
    request: Request,
    payload: ProfesionalRegisterCreate,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Create a usuario and its profesional profile in one request.

    Combines POST /auth/register + POST /users/me/profesional. Starts as
    estado_verificacion=pendiente; verification review happens out of band.
    Next: POST /auth/request-verify-token, POST /auth/verify, then
    POST /auth/jwt/login.
    """
    try:
        await user_manager.validate_password(payload.password, payload)
    except exceptions.InvalidPasswordException as exc:
        logger.warning("Profesional registration failed: invalid password")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.REGISTER_INVALID_PASSWORD,
                "reason": exc.reason,
            },
        )

    if await user_manager.user_db.get_by_email(payload.email) is not None:
        logger.warning("Profesional registration failed: user already exists")
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
        email=payload.email,
        hashed_password=user_manager.password_helper.hash(payload.password),
        nombre_completo=payload.nombre_completo,
        whatsapp=payload.whatsapp,
    )
    try:
        db.add(user)
        await db.flush()  # populate user.id without committing

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
            f"Profesional registration failed: integrity error email={payload.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration conflicts with an existing record",
        )
    await db.refresh(user)

    await user_manager.on_after_register(user, request)
    logger.info(f"Profesional registered usuario_id={user.id}")
    return user


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

    Complete with POST /auth/reset-password, then sign in with
    POST /auth/jwt/login.
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

    Start with POST /auth/forgot-password, then POST /auth/jwt/login.
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

    Then POST /auth/verify, then POST /auth/jwt/login.
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

    Request it with POST /auth/request-verify-token, then
    POST /auth/jwt/login.
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
