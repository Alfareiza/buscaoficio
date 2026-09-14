from uuid import uuid4

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

from .enums import (
    ComplejidadCategoria,
    EstadoPropuesta,
    EstadoSolicitud,
    EstadoVerificacionProfesional,
    IniciadaPor,
    ResultadoNegociacion,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    creado_en = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UsuarioProvisioningDisplayMixin:
    """Backs the admin-only usuario_email/password/nombre_completo/whatsapp
    form fields (app/admin.py's UsuarioProvisioningAdminMixin) with the
    linked Usuario's real values, so the Cliente/Profesional edit form can
    show and update them — without ever risking an async lazy-load crash if
    the `usuario` relationship happens not to be eager-loaded for a given
    fetch (e.g. a list-view row). sqlalchemy.inspect(self).unloaded is a
    synchronous, non-querying check: if `usuario` isn't already loaded, these
    just read as None (same as before eager loading existed) instead of
    touching the relationship at all.
    """

    def _loaded_usuario(self):
        if "usuario" in sa_inspect(self).unloaded:
            return None
        return self.usuario

    @property
    def usuario_email(self) -> str | None:
        usuario = self._loaded_usuario()
        return usuario.email if usuario else None

    @property
    def usuario_password(self) -> None:
        return None  # never echo the stored hash back

    @property
    def usuario_nombre_completo(self) -> str | None:
        usuario = self._loaded_usuario()
        return usuario.nombre_completo if usuario else None

    @property
    def usuario_whatsapp(self) -> str | None:
        usuario = self._loaded_usuario()
        return usuario.whatsapp if usuario else None


class User(SQLAlchemyBaseUserTableUUID, TimestampMixin, Base):
    __tablename__ = "usuarios"

    nombre_completo = Column(String, nullable=False)
    whatsapp = Column(String, nullable=True)
    # Google's OIDC "sub" (subject) claim — the permanent, unique ID Google
    # assigns to a Google Account. Unlike email, it never changes even if
    # the user later changes their Google email address, so it's what
    # actually identifies "this Google account" across logins. Nullable:
    # only set for accounts that have signed in with Google at least once
    # (see app/google_oauth_manager.py § "Google Sign-In").
    google_sub = Column(String, unique=True, nullable=True)
    # Soft-delete timestamp. A populated value means the account is gone for
    # login/admin listing, but the row stays so email/google_sub uniqueness
    # still blocks reuse. See UserManager.delete.
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship("Item", back_populates="user", cascade="all, delete-orphan")
    cliente = relationship(
        "Cliente", back_populates="usuario", uselist=False, cascade="all, delete-orphan"
    )
    profesional = relationship(
        "Profesional",
        back_populates="usuario",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __str__(self) -> str:
        return f"<{self.nombre_completo} ({self.email} - {self.whatsapp})>"


class Cliente(TimestampMixin, UsuarioProvisioningDisplayMixin, Base):
    __tablename__ = "clientes"

    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), primary_key=True)
    direccion_default = Column(String, nullable=True)
    zona_id = Column(
        UUID(as_uuid=True), ForeignKey("zonas_cobertura.id"), nullable=True
    )
    repeat_customer = Column(Boolean, default=False, nullable=False)
    referido_por_id = Column(
        UUID(as_uuid=True), ForeignKey("clientes.usuario_id"), nullable=True
    )

    usuario = relationship("User", back_populates="cliente")
    zona = relationship("ZonaCobertura")

    def __str__(self) -> str:
        usuario = self._loaded_usuario()
        if usuario is not None:
            return f"{usuario.nombre_completo} ({usuario.email})"
        return f"Cliente {self.usuario_nombre_completo}"


class Profesional(TimestampMixin, UsuarioProvisioningDisplayMixin, Base):
    __tablename__ = "profesionales"

    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), primary_key=True)

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

    def __str__(self) -> str:
        usuario = self._loaded_usuario()
        if usuario is not None:
            return f"{usuario.nombre_completo} ({usuario.email})"
        return f"Profesional {self.usuario_id}"


class Item(Base):
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)

    user = relationship("User", back_populates="items")


class RefreshToken(TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    refresh_token_hash = Column(String, nullable=False)
    fingerprint_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_ip = Column(String, nullable=True)

    user = relationship("User")


class EmailOtp(TimestampMixin, Base):
    """One-time passwordless login/registration codes, keyed by email rather
    than user_id — the email may not have an account yet (registration
    happens after a successful verify, not before)."""

    __tablename__ = "email_otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String, nullable=False, index=True)
    code_hash = Column(String, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_ip = Column(String, nullable=True)


class UsedGoogleSessionToken(TimestampMixin, Base):
    """Marks a google_session_token's `jti` as consumed the moment
    POST /auth/google/session successfully uses it, so the same token can't
    establish a second session if it leaks (e.g. via a URL captured in logs
    or Sentry request tracing) — it's a bearer credential that briefly rides
    in a redirect URL, unlike every other session-establishing token in this
    app which never leaves an HttpOnly cookie or a POST body. The token's
    own 2-minute expiry already bounds how long a leaked copy is dangerous;
    this closes the replay-within-that-window gap. No cleanup job purges old
    rows — same known gap as `refresh_tokens`/`email_otps`."""

    __tablename__ = "used_google_session_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    jti = Column(String, unique=True, nullable=False, index=True)


class CategoriaServicio(Base):
    __tablename__ = "categorias_servicio"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    nombre = Column(String(100), unique=True, nullable=False)
    complejidad = Column(
        String(10), nullable=False, default=ComplejidadCategoria.MEDIA.value
    )
    activa_v1 = Column(Boolean, nullable=False, default=False)
    orden_display = Column(SmallInteger, nullable=True)

    subcategorias = relationship(
        "SubcategoriaServicio",
        back_populates="categoria",
        cascade="all, delete-orphan",
    )

    def __str__(self) -> str:
        return self.nombre


class SubcategoriaServicio(Base):
    __tablename__ = "subcategorias_servicio"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    categoria_id = Column(
        UUID(as_uuid=True), ForeignKey("categorias_servicio.id"), nullable=False
    )
    nombre = Column(String(100), nullable=False)

    categoria = relationship("CategoriaServicio", back_populates="subcategorias")

    def __str__(self) -> str:
        return self.nombre


class ZonaCobertura(Base):
    __tablename__ = "zonas_cobertura"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    ciudad = Column(String(100), nullable=False)
    localidad = Column(String(100), nullable=True)
    activa_v1 = Column(Boolean, nullable=False, default=False)

    def __str__(self) -> str:
        if self.localidad:
            return f"{self.ciudad} — {self.localidad}"
        return self.ciudad


class ProfesionalCategoria(Base):
    __tablename__ = "profesional_categoria"

    usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("profesionales.usuario_id"),
        primary_key=True,
    )
    categoria_id = Column(
        UUID(as_uuid=True),
        ForeignKey("categorias_servicio.id"),
        primary_key=True,
    )


class ProfesionalZona(Base):
    __tablename__ = "profesional_zona"

    usuario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("profesionales.usuario_id"),
        primary_key=True,
    )
    zona_id = Column(
        UUID(as_uuid=True),
        ForeignKey("zonas_cobertura.id"),
        primary_key=True,
    )


class Solicitud(TimestampMixin, Base):
    """Pedido que publica un cliente: qué oficio necesita, dónde y con qué detalle.

    Es el punto de entrada del ciclo. Un profesional responde con una
    ``Propuesta``; si no se cierran en el precio, las ``Negociacion``
    (contraofertas) cuelgan de esa propuesta, no de la solicitud.
    """

    __tablename__ = "solicitudes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    cliente_id = Column(
        UUID(as_uuid=True), ForeignKey("clientes.usuario_id"), nullable=False
    )
    categoria_id = Column(
        UUID(as_uuid=True), ForeignKey("categorias_servicio.id"), nullable=False
    )
    subcategoria_id = Column(
        UUID(as_uuid=True), ForeignKey("subcategorias_servicio.id"), nullable=True
    )
    descripcion = Column(Text, nullable=False)
    fotos_urls = Column(JSON, nullable=True)
    presupuesto_aproximado = Column(Numeric(12, 2), nullable=True)
    es_urgente = Column(Boolean, nullable=False, default=False)
    estado = Column(String(30), nullable=False, default=EstadoSolicitud.PUBLICADA.value)
    # TODO: increment when a profesional is actually notified (email/WhatsApp).
    num_profesionales_notificados = Column(SmallInteger, nullable=False, default=0)
    primera_propuesta_en = Column(DateTime(timezone=True), nullable=True)
    zona_id = Column(
        UUID(as_uuid=True), ForeignKey("zonas_cobertura.id"), nullable=False
    )
    motivo_cancelamiento = Column(Text, nullable=True)

    cliente = relationship("Cliente")
    categoria = relationship("CategoriaServicio")
    zona = relationship("ZonaCobertura")
    propuestas = relationship("Propuesta", back_populates="solicitud")

    def __str__(self) -> str:
        return f"Solicitud de {self.categoria.nombre} {self.creado_en:%Y/%m/%d/%H/%M}"


class Propuesta(TimestampMixin, Base):
    """Oferta de un profesional a una ``Solicitud`` (precio, plazo, enfoque).

    Varias propuestas pueden apuntar a la misma solicitud. El
    ``precio_inicial`` es el P₀ de las ``Negociacion``: las contraofertas
    no pueden bajar de ~80% de ese valor (regla de negocio, no de esta
    tabla).
    """

    __tablename__ = "propuestas"
    __table_args__ = (
        CheckConstraint(
            "plazo_ejecucion_dias IS NULL OR plazo_ejecucion_dias >= 1",
            name="propuestas_plazo_min_1",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    solicitud_id = Column(
        UUID(as_uuid=True), ForeignKey("solicitudes.id"), nullable=False
    )
    profesional_id = Column(
        UUID(as_uuid=True), ForeignKey("profesionales.usuario_id"), nullable=False
    )
    precio_inicial = Column(Numeric(12, 2), nullable=False)
    plazo_ejecucion_dias = Column(SmallInteger, nullable=True)
    descripcion_enfoque = Column(Text, nullable=True)
    estado = Column(String(30), nullable=False, default=EstadoPropuesta.ENVIADA.value)
    motivo_cancelamiento = Column(Text, nullable=True)
    motivo_rechazo = Column(Text, nullable=True)

    solicitud = relationship("Solicitud", back_populates="propuestas")
    profesional = relationship("Profesional")

    def __str__(self) -> str:
        return f"Propuesta {self.id}"


class Negociacion(TimestampMixin, Base):
    """Una ronda de contraoferta sobre una ``Propuesta`` (máximo 2).

    No vive suelta: siempre pertenece a una propuesta, y por ella a la
    ``Solicitud``. ``iniciada_por`` dice si el movimiento lo hizo el
    cliente o el profesional. ``precio_propuesto`` debe ser mayor que 0.
    """

    __tablename__ = "negociaciones"
    __table_args__ = (
        CheckConstraint("ronda <= 2", name="negociaciones_ronda_max_2"),
        CheckConstraint("precio_propuesto > 0", name="negociaciones_precio_positivo"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    propuesta_id = Column(
        UUID(as_uuid=True), ForeignKey("propuestas.id"), nullable=False
    )
    ronda = Column(SmallInteger, nullable=False)
    iniciada_por = Column(String(20), nullable=False, default=IniciadaPor.CLIENTE.value)
    precio_propuesto = Column(Numeric(12, 2), nullable=False)
    resultado = Column(
        String(20), nullable=False, default=ResultadoNegociacion.PENDIENTE.value
    )

    propuesta = relationship("Propuesta")

    def __str__(self) -> str:
        return f"Negociación {self.id} ronda {self.ronda}"
