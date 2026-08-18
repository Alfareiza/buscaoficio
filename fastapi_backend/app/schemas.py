import uuid
from datetime import datetime

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr
from uuid import UUID

from .enums import EstadoVerificacionProfesional, TipoDocumento


class UserRead(schemas.BaseUser[uuid.UUID]):
    nombre_completo: str
    whatsapp: str | None = None


class UserCreate(schemas.BaseUserCreate):
    nombre_completo: str
    whatsapp: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    nombre_completo: str | None = None
    whatsapp: str | None = None


class ItemBase(BaseModel):
    name: str
    description: str | None = None
    quantity: int | None = None


class ItemCreate(ItemBase):
    pass


class ItemRead(ItemBase):
    id: UUID
    user_id: UUID

    model_config = {"from_attributes": True}


class ClienteBase(BaseModel):
    direccion_default: str | None = None
    referido_por_id: UUID | None = None


class ClienteUpdate(BaseModel):
    direccion_default: str | None = None


class ClienteAdminUpdate(ClienteUpdate):
    repeat_customer: bool | None = None


class ClienteRead(ClienteBase):
    usuario_id: UUID
    repeat_customer: bool
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class ProfesionalBase(BaseModel):
    documento_tipo: TipoDocumento
    documento_numero: str
    anos_experiencia: int | None = None
    foto_perfil_url: str | None = None


class ProfesionalUpdate(BaseModel):
    anos_experiencia: int | None = None
    foto_perfil_url: str | None = None


class ProfesionalAdminUpdate(ProfesionalUpdate):
    estado_verificacion: EstadoVerificacionProfesional | None = None
    score_calificacion: int | None = None
    whatsapp_verificado: bool | None = None
    contrato_aceptado: bool | None = None
    trabajos_gratis_restantes: int | None = None


class ProfesionalRead(ProfesionalBase):
    usuario_id: UUID
    estado_verificacion: EstadoVerificacionProfesional
    score_calificacion: int | None = None
    whatsapp_verificado: bool
    contrato_aceptado: bool
    contrato_aceptado_en: datetime | None = None
    trabajos_gratis_restantes: int
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class OtpRequestIn(BaseModel):
    email: EmailStr


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str


class ClienteRegisterOtpCreate(ClienteBase):
    """Payload for passwordless cliente registration — no password; email
    ownership is proven by a short-lived registration_token from
    /auth/otp/verify instead."""

    registration_token: str
    nombre_completo: str
    whatsapp: str | None = None


class ProfesionalRegisterOtpCreate(ProfesionalBase):
    """Payload for passwordless profesional registration. See
    ClienteRegisterOtpCreate for the general pattern."""

    registration_token: str
    nombre_completo: str
    whatsapp: str | None = None
