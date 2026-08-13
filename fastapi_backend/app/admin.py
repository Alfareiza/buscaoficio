import uuid

from fastadmin import SqlAlchemyModelAdmin, WidgetType, register
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import select, update

from .database import async_session_maker
from .models import User


@register(User, sqlalchemy_sessionmaker=async_session_maker)
class UserAdmin(SqlAlchemyModelAdmin):
    exclude = ("hash_password",)
    list_display = ("id", "email", "is_superuser", "is_active")
    list_display_links = ("id", "email")
    list_filter = ("id", "email", "is_superuser", "is_active")
    search_fields = ("email",)
    formfield_overrides = {  # noqa: RUF012
        "username": (WidgetType.SlugInput, {"required": True}),
        "hashed_password": (WidgetType.PasswordInput, {"passwordModalForm": True}),
        "avatar_url": (
            WidgetType.UploadImage,
            {
                "required": False,
                # Disable crop image for upload field
                # "disableCropImage": True,
            },
        ),
    }

    @property
    def hasher(self):
        if not hasattr(self, '_hasher'):
            self._hasher = Argon2Hasher()
        return self._hasher

    async def authenticate(self, email: str, password: str) -> uuid.UUID | int | None:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            qry = await session.scalars(
                select(self.model_cls).filter_by(email=email, is_superuser=True)
            )
            if not (user := qry.first()):
                return None

            if not self.hasher.verify(password, user.hashed_password):
                return None

            return user.id

    async def change_password(self, id: uuid.UUID | int, password: str) -> None:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as session:
            new_password = self.hasher.hash(password)
            query = (
                update(self.model_cls)
                .where(User.id.in_([id]))
                .values(hashed_password=new_password)
            )
            await session.execute(query)
            await session.commit()