import re
import uuid
from datetime import datetime

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator
from uuid import UUID

from .enums import EstadoVerificacionProfesional, TipoDocumento

DOCUMENTO_NUMERO_REGEX = {
    TipoDocumento.CC: re.compile(r"^\d{5,10}$"),
    TipoDocumento.CE: re.compile(r"^\d{6,8}$"),
    TipoDocumento.PA: re.compile(r"^[A-Z0-9]{6,12}$"),
    TipoDocumento.PE: re.compile(r"^[A-Z0-9]{8,16}$"),
    TipoDocumento.PT: re.compile(r"^\d{6,10}$"),
}


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
    zona_ids: list[UUID] = Field(min_length=1)
    categoria_ids: list[UUID] = Field(min_length=1)

    @field_validator("documento_numero")
    @classmethod
    def documento_matches_tipo(cls, value: str, info: ValidationInfo) -> str:
        tipo = info.data.get("documento_tipo")
        pattern = DOCUMENTO_NUMERO_REGEX.get(tipo)
        if pattern is None or not pattern.fullmatch(value):
            raise ValueError("documento_numero does not match documento_tipo")
        return value


class CategoriaServicioRead(BaseModel):
    id: UUID
    nombre: str
    complejidad: str
    activa_v1: bool
    orden_display: int | None = None

    model_config = {"from_attributes": True}


class ZonaCoberturaRead(BaseModel):
    id: UUID
    ciudad: str
    localidad: str | None = None
    activa_v1: bool

    model_config = {"from_attributes": True}
