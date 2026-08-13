from enum import Enum


class TipoDocumento(str, Enum):
    CC = "CC"
    CE = "CE"
    PASAPORTE = "PASAPORTE"


class EstadoVerificacionProfesional(str, Enum):
    PENDIENTE = "pendiente"
    VERIFICADO = "verificado"
    REVISAR_MANUAL = "revisar_manual"
    RECHAZADO = "rechazado"
