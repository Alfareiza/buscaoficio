"use server";

import * as Sentry from "@sentry/nextjs";
import { cookies } from "next/headers";

import {
  authOtpRequest,
  authOtpVerify,
  registerRegisterClienteOtp,
  registerRegisterProfesionalOtp,
  type TipoDocumento,
} from "@/app/clientService";
import { forwardAuthCookies, setAccessTokenCookie } from "@/lib/auth-cookies";
import {
  onboardingClienteSchema,
  onboardingProfesionalSchema,
  otpRequestSchema,
  otpVerifySchema,
} from "@/lib/definitions";

type ActionResult<T> = { ok: true; data: T } | { ok: false; error: string };

type SessionData = { status: "existing_user"; hasRole: boolean };
type NewUserData = { status: "new_user"; registrationToken: string };

function extractErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (
      detail &&
      typeof detail === "object" &&
      "reason" in detail &&
      typeof (detail as { reason: unknown }).reason === "string"
    ) {
      return (detail as { reason: string }).reason;
    }
  }
  return "Ocurrió un error inesperado. Intenta de nuevo.";
}

/** Sets the accessToken/refreshToken/fingerprintToken cookies from a
 * successful session response (OTP verify or OTP registration) — shared so
 * the cookie-forwarding logic exists in exactly one place. */
async function persistSession(
  data: unknown,
  setCookieHeaders: string[] | undefined,
): Promise<SessionData | null> {
  if (
    !data ||
    typeof data !== "object" ||
    !("access_token" in data) ||
    typeof (data as { access_token: unknown }).access_token !== "string"
  ) {
    return null;
  }
  const accessToken = (data as { access_token: string }).access_token;
  const hasRole =
    "has_role" in data &&
    typeof (data as { has_role: unknown }).has_role === "boolean"
      ? (data as { has_role: boolean }).has_role
      : true;

  const cookieStore = await cookies();
  setAccessTokenCookie(cookieStore, accessToken);
  forwardAuthCookies(setCookieHeaders, cookieStore);

  return { status: "existing_user", hasRole };
}

export async function requestOtpAction(
  email: string,
): Promise<ActionResult<null>> {
  const validated = otpRequestSchema.safeParse({ email });
  if (!validated.success) {
    return { ok: false, error: "Correo electrónico inválido" };
  }

  try {
    const { error } = await authOtpRequest({ body: { email } });
    if (error) {
      return { ok: false, error: extractErrorMessage(error) };
    }
    return { ok: true, data: null };
  } catch (error) {
    Sentry.captureException(error);
    return {
      ok: false,
      error: "No pudimos enviar el código. Intenta de nuevo.",
    };
  }
}

export async function verifyOtpAction(
  email: string,
  code: string,
): Promise<ActionResult<SessionData | NewUserData>> {
  const validated = otpVerifySchema.safeParse({ email, code });
  if (!validated.success) {
    return { ok: false, error: "Código inválido" };
  }

  try {
    const result = await authOtpVerify({ body: { email, code } });
    const { data, error } = result;
    if (error) {
      return { ok: false, error: extractErrorMessage(error) };
    }

    if (data && typeof data === "object" && "registration_token" in data) {
      return {
        ok: true,
        data: {
          status: "new_user",
          registrationToken: (data as { registration_token: string })
            .registration_token,
        },
      };
    }

    const session = await persistSession(
      data,
      result.headers?.["set-cookie"] as string[] | undefined,
    );
    if (!session) {
      return {
        ok: false,
        error: "Ocurrió un error inesperado. Intenta de nuevo.",
      };
    }
    return { ok: true, data: session };
  } catch (error) {
    Sentry.captureException(error);
    return {
      ok: false,
      error: "No pudimos verificar el código. Intenta de nuevo.",
    };
  }
}

export async function registerClienteOtpAction(payload: {
  registration_token: string;
  nombre_completo: string;
  whatsapp?: string;
}): Promise<ActionResult<SessionData>> {
  const validated = onboardingClienteSchema.safeParse(payload);
  if (!validated.success) {
    return { ok: false, error: "Datos inválidos" };
  }

  try {
    const result = await registerRegisterClienteOtp({ body: validated.data });
    const { data, error } = result;
    if (error) {
      return { ok: false, error: extractErrorMessage(error) };
    }
    const session = await persistSession(
      data,
      result.headers?.["set-cookie"] as string[] | undefined,
    );
    if (!session) {
      return {
        ok: false,
        error: "Ocurrió un error inesperado. Intenta de nuevo.",
      };
    }
    return { ok: true, data: session };
  } catch (error) {
    Sentry.captureException(error);
    return {
      ok: false,
      error: "No pudimos crear tu cuenta. Intenta de nuevo.",
    };
  }
}

export async function registerProfesionalOtpAction(payload: {
  registration_token: string;
  nombre_completo: string;
  whatsapp?: string;
  documento_tipo: TipoDocumento;
  documento_numero: string;
}): Promise<ActionResult<SessionData>> {
  const validated = onboardingProfesionalSchema.safeParse(payload);
  if (!validated.success) {
    return { ok: false, error: "Datos inválidos" };
  }

  try {
    const result = await registerRegisterProfesionalOtp({
      body: { ...validated.data, documento_tipo: payload.documento_tipo },
    });
    const { data, error } = result;
    if (error) {
      return { ok: false, error: extractErrorMessage(error) };
    }
    const session = await persistSession(
      data,
      result.headers?.["set-cookie"] as string[] | undefined,
    );
    if (!session) {
      return {
        ok: false,
        error: "Ocurrió un error inesperado. Intenta de nuevo.",
      };
    }
    return { ok: true, data: session };
  } catch (error) {
    Sentry.captureException(error);
    return {
      ok: false,
      error: "No pudimos crear tu cuenta. Intenta de nuevo.",
    };
  }
}
