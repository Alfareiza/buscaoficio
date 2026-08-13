from uuid import uuid4

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

from .enums import EstadoVerificacionProfesional


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(SQLAlchemyBaseUserTableUUID, TimestampMixin, Base):
    __tablename__ = "usuarios"

    nombre_completo = Column(String, nullable=False)
    whatsapp = Column(String, nullable=True)

    items = relationship("Item", back_populates="user", cascade="all, delete-orphan")
    cliente = relationship(
        "Cliente", back_populates="usuario", uselist=False, cascade="all, delete-orphan"
    )
    profesional = relationship(
        "Profesional", back_populates="usuario", uselist=False, cascade="all, delete-orphan"
    )


class Cliente(TimestampMixin, Base):
    __tablename__ = "clientes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), unique=True, nullable=False)
    direccion_default = Column(String, nullable=True)
    repeat_customer = Column(Boolean, default=False, nullable=False)
    referido_por_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=True)

    usuario = relationship("User", back_populates="cliente")


class Profesional(TimestampMixin, Base):
    __tablename__ = "profesionales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), unique=True, nullable=False)

    documento_tipo = Column(String, nullable=False)
    documento_numero = Column(String, unique=True, nullable=False)
    anos_experiencia = Column(Integer, nullable=True)
    foto_perfil_url = Column(String, nullable=True)

    terminos_aceptados = Column(Boolean, default=False, nullable=False)
    terminos_aceptados_en = Column(DateTime(timezone=True), nullable=True)

    score_calificacion = Column(Integer, nullable=True)
    estado_verificacion = Column(
        String, default=EstadoVerificacionProfesional.PENDIENTE.value, nullable=False
    )

    whatsapp_verificado = Column(Boolean, default=False, nullable=False)

    contrato_aceptado = Column(Boolean, default=False, nullable=False)
    contrato_aceptado_en = Column(DateTime(timezone=True), nullable=True)
    contrato_aceptado_ip = Column(String, nullable=True)

    trabajos_gratis_restantes = Column(Integer, default=3, nullable=False)

    usuario = relationship("User", back_populates="profesional")


class Item(Base):
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)

    user = relationship("User", back_populates="items")
