import type { TipoDocumento } from "@/app/clientService";

/** Format checks for the tipos we collect on profesional signup. */
export const DOCUMENTO_NUMERO_REGEX: Record<TipoDocumento, RegExp> = {
  CC: /^\d{5,10}$/,
  CE: /^\d{6,8}$/,
  PA: /^[A-Z0-9]{6,12}$/,
  PE: /^[A-Z0-9]{8,16}$/,
  PT: /^\d{6,10}$/,
};

export const DOCUMENTO_NUMERO_HINT: Record<TipoDocumento, string> = {
  CC: "Ingresa 5 a 10 dígitos",
  CE: "Ingresa 6 a 8 dígitos",
  PA: "Ingresa 6 a 12 letras o números",
  PE: "Ingresa 8 a 16 letras o números",
  PT: "Ingresa 6 a 10 dígitos",
};

const DIGITS_ONLY: ReadonlySet<TipoDocumento> = new Set(["CC", "CE", "PT"]);

export function sanitizeDocumentoNumero(
  tipo: TipoDocumento | "",
  raw: string,
): string {
  if (tipo === "PA" || tipo === "PE") {
    return raw.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  }
  if (!tipo || DIGITS_ONLY.has(tipo)) {
    return raw.replace(/\D/g, "");
  }
  return raw;
}

export function isValidColombianDocumento(
  tipo: TipoDocumento | "",
  numero: string,
): boolean {
  if (!tipo) return false;
  return DOCUMENTO_NUMERO_REGEX[tipo].test(numero);
}
