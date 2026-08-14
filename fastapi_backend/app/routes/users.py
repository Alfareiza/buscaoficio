from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi_users import exceptions
from fastapi_users.router.common import ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import logger
from app.database import get_async_session
from app.models import Cliente, Profesional, User
from app.schemas import (
    ClienteAdminUpdate,
    ClienteRead,
    ClienteUpdate,
    ProfesionalAdminUpdate,
    ProfesionalRead,
    ProfesionalUpdate,
    UserRead,
    UserUpdate,
)
from app.users import (
    UserManager,
    current_active_user,
    current_superuser,
    get_user_manager,
)

router = APIRouter(tags=["users"])


async def get_user_or_404(
    id: str,
    user_manager: UserManager = Depends(get_user_manager),
) -> User:
    try:
        parsed_id = user_manager.parse_id(id)
        return await user_manager.get(parsed_id)
    except (exceptions.UserNotExists, exceptions.InvalidID) as exc:
        logger.warning(f"User not found id={id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc


@router.get(
    "/me",
    summary="Current authenticated user",
    response_model=UserRead,
    name="users:current_user",
)
async def get_me(user: User = Depends(current_active_user)):
    """Return the current authenticated user.

    Requires POST /auth/jwt/login.
    """
    return user


@router.patch(
    "/me",
    summary="Update current user",
    response_model=UserRead,
    name="users:patch_current_user",
)
async def update_me(
    request: Request,
    user_update: UserUpdate,
    user: User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Update the current authenticated user.

    Requires POST /auth/jwt/login. Superusers can PATCH /users/{id}
    instead.
    """
    try:
        updated = await user_manager.update(
            user_update, user, safe=True, request=request
        )
        logger.info(f"Current user updated user_id={user.id}")
        return updated
    except exceptions.InvalidPasswordException as exc:
        logger.warning(
            f"Current user update failed: invalid password user_id={user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.UPDATE_USER_INVALID_PASSWORD,
                "reason": exc.reason,
            },
        )
    except exceptions.UserAlreadyExists:
        logger.warning(f"Current user update failed: email exists user_id={user.id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS,
        )


@router.get(
    "/{id}",
    summary="Get user by id (superuser)",
    response_model=UserRead,
    dependencies=[Depends(current_superuser)],
    name="users:user",
)
async def get_user(user: User = Depends(get_user_or_404)):
    """Get user by id.

    Superuser only after POST /auth/jwt/login. Use GET /users/me for
    the current user.
    """
    return user


@router.patch(
    "/{id}",
    summary="Update user by id (superuser)",
    response_model=UserRead,
    dependencies=[Depends(current_superuser)],
    name="users:patch_user",
)
async def update_user(
    user_update: UserUpdate,
    request: Request,
    user: User = Depends(get_user_or_404),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Update user by id.

    Superuser only after POST /auth/jwt/login. Use PATCH /users/me for
    the current user.
    """
    try:
        updated = await user_manager.update(
            user_update, user, safe=False, request=request
        )
        logger.info(f"User updated user_id={user.id}")
        return updated
    except exceptions.InvalidPasswordException as exc:
        logger.warning(f"User update failed: invalid password user_id={user.id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.UPDATE_USER_INVALID_PASSWORD,
                "reason": exc.reason,
            },
        )
    except exceptions.UserAlreadyExists:
        logger.warning(f"User update failed: email exists user_id={user.id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS,
        )


@router.delete(
    "/{id}",
    summary="Delete user by id (superuser)",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(current_superuser)],
    name="users:delete_user",
)
async def delete_user(
    request: Request,
    user: User = Depends(get_user_or_404),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Delete user by id.

    Superuser only after POST /auth/jwt/login. This also removes that
    user's items.
    """
    await user_manager.delete(user, request=request)
    logger.info(f"User deleted user_id={user.id}")
    return None


async def get_cliente_or_404(usuario_id, db: AsyncSession) -> Cliente:
    result = await db.execute(select(Cliente).filter(Cliente.usuario_id == usuario_id))
    cliente = result.scalars().first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cliente profile not found"
        )
    return cliente


async def get_profesional_or_404(usuario_id, db: AsyncSession) -> Profesional:
    result = await db.execute(
        select(Profesional).filter(Profesional.usuario_id == usuario_id)
    )
    profesional = result.scalars().first()
    if not profesional:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profesional profile not found",
        )
    return profesional


# --- Cliente: self-service (current user) ---


@router.get(
    "/me/cliente",
    tags=["clientes"],
    summary="Get current user's cliente profile",
    response_model=ClienteRead,
    name="clientes:read_me",
)
async def get_my_cliente(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get the current user's cliente profile.

    Requires POST /auth/jwt/login.
    """
    return await get_cliente_or_404(user.id, db)


@router.patch(
    "/me/cliente",
    tags=["clientes"],
    summary="Update current user's cliente profile",
    response_model=ClienteRead,
    name="clientes:update_me",
)
async def update_my_cliente(
    cliente_update: ClienteUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Update the current user's cliente profile.

    Requires POST /auth/jwt/login.
    """
    cliente = await get_cliente_or_404(user.id, db)
    for field, value in cliente_update.model_dump(exclude_unset=True).items():
        setattr(cliente, field, value)
    await db.commit()
    await db.refresh(cliente)
    logger.info(f"Cliente profile updated usuario_id={user.id}")
    return cliente


@router.delete(
    "/me/cliente",
    tags=["clientes"],
    summary="Delete current user's cliente profile",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    name="clientes:delete_me",
)
async def delete_my_cliente(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Delete the current user's cliente profile.

    Requires POST /auth/jwt/login.
    """
    cliente = await get_cliente_or_404(user.id, db)
    await db.delete(cliente)
    await db.commit()
    logger.info(f"Cliente profile deleted usuario_id={user.id}")
    return None


# --- Cliente: by user id (superuser) ---


@router.get(
    "/{id}/cliente",
    tags=["clientes"],
    summary="Get cliente profile by user id (superuser)",
    response_model=ClienteRead,
    dependencies=[Depends(current_superuser)],
    name="clientes:read",
)
async def get_cliente(
    db: AsyncSession = Depends(get_async_session),
    target_user: User = Depends(get_user_or_404),
):
    """Get a cliente profile by user id.

    Superuser only after POST /auth/jwt/login. Use GET /users/me/cliente
    for the current user.
    """
    return await get_cliente_or_404(target_user.id, db)


@router.patch(
    "/{id}/cliente",
    tags=["clientes"],
    summary="Update cliente profile by user id (superuser)",
    response_model=ClienteRead,
    dependencies=[Depends(current_superuser)],
    name="clientes:update",
)
async def update_cliente(
    cliente_update: ClienteAdminUpdate,
    db: AsyncSession = Depends(get_async_session),
    target_user: User = Depends(get_user_or_404),
):
    """Update a cliente profile by user id.

    Superuser only after POST /auth/jwt/login. Use PATCH /users/me/cliente
    for the current user.
    """
    cliente = await get_cliente_or_404(target_user.id, db)
    for field, value in cliente_update.model_dump(exclude_unset=True).items():
        setattr(cliente, field, value)
    await db.commit()
    await db.refresh(cliente)
    logger.info(f"Cliente profile updated (admin) usuario_id={target_user.id}")
    return cliente


@router.delete(
    "/{id}/cliente",
    tags=["clientes"],
    summary="Delete cliente profile by user id (superuser)",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(current_superuser)],
    name="clientes:delete",
)
async def delete_cliente(
    db: AsyncSession = Depends(get_async_session),
    target_user: User = Depends(get_user_or_404),
):
    """Delete a cliente profile by user id.

    Superuser only after POST /auth/jwt/login.
    """
    cliente = await get_cliente_or_404(target_user.id, db)
    await db.delete(cliente)
    await db.commit()
    logger.info(f"Cliente profile deleted (admin) usuario_id={target_user.id}")
    return None


# --- Profesional: self-service (current user) ---


@router.get(
    "/me/profesional",
    tags=["profesionales"],
    summary="Get current user's profesional profile",
    response_model=ProfesionalRead,
    name="profesionales:read_me",
)
async def get_my_profesional(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get the current user's profesional profile.

    Requires POST /auth/jwt/login.
    """
    return await get_profesional_or_404(user.id, db)


@router.patch(
    "/me/profesional",
    tags=["profesionales"],
    summary="Update current user's profesional profile",
    response_model=ProfesionalRead,
    name="profesionales:update_me",
)
async def update_my_profesional(
    profesional_update: ProfesionalUpdate,
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Update the current user's profesional profile.

    Requires POST /auth/jwt/login. Only self-editable fields
    (anos_experiencia, foto_perfil_url) - verification/contract fields are
    superuser-only via PATCH /users/{id}/profesional.
    """
    profesional = await get_profesional_or_404(user.id, db)
    for field, value in profesional_update.model_dump(exclude_unset=True).items():
        setattr(profesional, field, value)
    await db.commit()
    await db.refresh(profesional)
    logger.info(f"Profesional profile updated usuario_id={user.id}")
    return profesional


@router.delete(
    "/me/profesional",
    tags=["profesionales"],
    summary="Delete current user's profesional profile",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    name="profesionales:delete_me",
)
async def delete_my_profesional(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Delete the current user's profesional profile.

    Requires POST /auth/jwt/login.
    """
    profesional = await get_profesional_or_404(user.id, db)
    await db.delete(profesional)
    await db.commit()
    logger.info(f"Profesional profile deleted usuario_id={user.id}")
    return None


# --- Profesional: by user id (superuser) ---


@router.get(
    "/{id}/profesional",
    tags=["profesionales"],
    summary="Get profesional profile by user id (superuser)",
    response_model=ProfesionalRead,
    dependencies=[Depends(current_superuser)],
    name="profesionales:read",
)
async def get_profesional(
    db: AsyncSession = Depends(get_async_session),
    target_user: User = Depends(get_user_or_404),
):
    """Get a profesional profile by user id.

    Superuser only after POST /auth/jwt/login. Use GET
    /users/me/profesional for the current user.
    """
    return await get_profesional_or_404(target_user.id, db)


@router.patch(
    "/{id}/profesional",
    tags=["profesionales"],
    summary="Update profesional profile by user id (superuser)",
    response_model=ProfesionalRead,
    dependencies=[Depends(current_superuser)],
    name="profesionales:update",
)
async def update_profesional(
    profesional_update: ProfesionalAdminUpdate,
    db: AsyncSession = Depends(get_async_session),
    target_user: User = Depends(get_user_or_404),
):
    """Update a profesional profile by user id, including verification and
    contract fields.

    Superuser only after POST /auth/jwt/login. Use PATCH
    /users/me/profesional for self-editable fields only.
    """
    profesional = await get_profesional_or_404(target_user.id, db)
    for field, value in profesional_update.model_dump(exclude_unset=True).items():
        setattr(profesional, field, value)
    await db.commit()
    await db.refresh(profesional)
    logger.info(f"Profesional profile updated (admin) usuario_id={target_user.id}")
    return profesional


@router.delete(
    "/{id}/profesional",
    tags=["profesionales"],
    summary="Delete profesional profile by user id (superuser)",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(current_superuser)],
    name="profesionales:delete",
)
async def delete_profesional(
    db: AsyncSession = Depends(get_async_session),
    target_user: User = Depends(get_user_or_404),
):
    """Delete a profesional profile by user id.

    Superuser only after POST /auth/jwt/login.
    """
    profesional = await get_profesional_or_404(target_user.id, db)
    await db.delete(profesional)
    await db.commit()
    logger.info(f"Profesional profile deleted (admin) usuario_id={target_user.id}")
    return None
