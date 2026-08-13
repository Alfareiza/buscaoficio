"""
Authentication routes for Buscaoficio.

All flows (register, login, logout, email verification, password reset) are
documented in docs/auth.md at the repository root. Read that first if you are
new to the project — it explains why these routes exist explicitly instead of
relying on fastapi-users' built-in router, how permissions work, and how to
create a superuser.
"""
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions
from fastapi_users.authentication import Strategy
from fastapi_users.router.common import ErrorCode
from pydantic import EmailStr

from app.config import logger
from app.models import User
from app.schemas import UserCreate, UserRead
from app.users import UserManager, auth_backend, current_user_token, get_user_manager

router = APIRouter(tags=["auth"])


@router.post("/jwt/login", summary="Login → JWT", name="auth:jwt.login")
async def login(
    request: Request,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
):
    """Login and return a JWT.

    Create the user with POST /auth/register first. Optional:
    POST /auth/request-verify-token then POST /auth/verify.
    """
    user = await user_manager.authenticate(credentials)

    if user is None or not user.is_active:
        logger.warning(f"Login failed for username={credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
        )

    response = await auth_backend.login(strategy, user)
    await user_manager.on_after_login(user, request, response)
    logger.info(f"User {user.id} logged in")
    return response


@router.post("/jwt/logout", summary="Logout", name="auth:jwt.logout")
async def logout(
    user_token: tuple[User, str] = Depends(current_user_token),
    strategy: Strategy[User, UUID] = Depends(auth_backend.get_strategy),
):
    """Invalidate the current JWT.

    Call after POST /auth/jwt/login when the user signs out.
    """
    user, token = user_token
    return await auth_backend.logout(strategy, user, token)


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
