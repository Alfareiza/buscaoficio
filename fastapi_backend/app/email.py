from pathlib import Path
import urllib.parse

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from .config import logger, settings
from .models import User


def get_email_config():
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
        USE_CREDENTIALS=settings.USE_CREDENTIALS,
        VALIDATE_CERTS=settings.VALIDATE_CERTS,
        TEMPLATE_FOLDER=Path(__file__).parent / settings.TEMPLATE_DIR,
    )
    return conf


async def send_reset_password_email(user: User, token: str):
    conf = get_email_config()
    email = user.email
    base_url = f"{settings.FRONTEND_URL}/password-recovery/confirm?"
    params = {"token": token}
    encoded_params = urllib.parse.urlencode(params)
    link = f"{base_url}{encoded_params}"
    message = MessageSchema(
        subject="🔒 Recuperar Contraseña - Busca oficio",
        recipients=[email],
        template_body={"username": email, "link": link},
        subtype=MessageType.html,
    )

    try:
        fm = FastMail(conf)
        await fm.send_message(message, template_name="password_reset.html")
    except Exception:
        logger.exception(f"Falló el envío de correo que restablece la contraseña del usuaario {user.id!r}")
        raise

    logger.info(f"Password reset email enviado a usario {user.id!r}")


async def send_otp_code_email(email: str, code: str):
    """Send a passwordless-login OTP code. Unlike send_reset_password_email,
    there is no User object yet — the email may belong to a not-yet-created
    account (see docs/auth.md § passwordless auth)."""
    conf = get_email_config()
    message = MessageSchema(
        subject="🔑 Tu código de acceso - Busca oficio",
        recipients=[email],
        template_body={"code": code},
        subtype=MessageType.html,
    )

    try:
        fm = FastMail(conf)
        await fm.send_message(message, template_name="otp_code.html")
    except Exception:
        logger.exception(f"Falló el envío del código OTP a {email!r}")
        raise

    logger.info(f"Código OTP enviado a {email!r}")
