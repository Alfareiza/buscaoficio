from enum import Enum


class TipoDocumento(str, Enum):
    """Each member carries a human-readable Spanish label alongside its code
    (e.g. TipoDocumento.CC.label == "Cédula de Ciudadanía"), used to render
    admin dropdown options — the codes alone aren't self-explanatory.
    """

    def __new__(cls, code: str, label: str) -> "TipoDocumento":
        obj = str.__new__(cls, code)
        obj._value_ = code
        obj.label = label
        return obj

    CC = ("CC", "Cédula de Ciudadanía")
    CE = ("CE", "Cédula de Extranjería")
    # TI = ("TI", "Tarjeta de Identidad")
    # RC = ("RC", "Registro Civil")
    PA = ("PA", "Pasaporte")
    # MS = ("MS", "Menor sin Identificación")
    PE = ("PE", "Permiso Especial")
    # CN = ("CN", "Certificado Nacido Vivo")
    PT = ("PT", "Permiso Temporal")
    # SC = ("SC", "Salvo Conducto")


class EstadoVerificacionProfesional(str, Enum):
    PENDIENTE = "pendiente"
    VERIFICADO = "verificado"
    REVISAR_MANUAL = "revisar_manual"
    RECHAZADO = "rechazado"
