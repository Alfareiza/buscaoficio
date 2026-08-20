"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Check } from "lucide-react";
import { FaGoogle } from "react-icons/fa";

import { OtpCodeInput } from "@/components/auth/OtpCodeInput";
import {
  BuscaOficioMark,
  BuscaOficioWordmark,
} from "@/components/ui/BuscaOficioLogo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  requestOtpAction,
  verifyOtpAction,
  registerClienteOtpAction,
  registerProfesionalOtpAction,
} from "@/components/actions/otp-auth-action";
import type { TipoDocumento } from "@/app/clientService";
import {
  isValidColombianMobile,
  sanitizeColombianMobileInput,
  toE164ColombianMobile,
} from "@/lib/colombian-mobile";
import { cn } from "@/lib/utils";

type Step = "email" | "otp" | "onboarding-name" | "onboarding-role";
type Role = "cliente" | "profesional";

const DOCUMENTO_TIPOS: { value: TipoDocumento; label: string }[] = [
  { value: "CC", label: "Cédula de Ciudadanía" },
  { value: "CE", label: "Cédula de Extranjería" },
  // { value: "TI", label: "Tarjeta de Identidad" },
  // { value: "RC", label: "Registro Civil" },
  { value: "PA", label: "Pasaporte" },
  // { value: "MS", label: "Menor sin Identificación" },
  { value: "PE", label: "Permiso Especial" },
  // { value: "CN", label: "Certificado Nacido Vivo" },
  { value: "PT", label: "Permiso Temporal" },
  // { value: "SC", label: "Salvo Conducto" },
];

interface AuthCardProps {
  mode: "page" | "modal";
  intent?: "login" | "register";
  onSuccess?: () => void;
}

const INTENT_COPY = {
  login: {
    subtitle: "Para solicitar un servicio, inicia sesión o crea una cuenta",
    toggleLead: "No tengo cuenta.",
    toggleAction: "Registrarme",
    toggleHref: "/register",
  },
  register: {
    subtitle: "Crea una cuenta y descubre lo que puedes encontrar",
    toggleLead: "Ya tengo una cuenta.",
    toggleAction: "Iniciar Sesión",
    toggleHref: "/login",
  },
} as const;

// Keep in sync with OtpManager.RESEND_COOLDOWN_SECONDS — the backend
// silently no-ops a resend inside this window (anti-enumeration 202).
const OTP_RESEND_COOLDOWN_SECONDS = 60;

export function AuthCard({ mode, intent = "login", onSuccess }: AuthCardProps) {
  const router = useRouter();
  const copy = INTENT_COPY[intent];

  const [step, setStep] = useState<Step>("email");
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shakeOtp, setShakeOtp] = useState(false);
  const [otpResetKey, setOtpResetKey] = useState(0);
  const [resendIn, setResendIn] = useState(0);
  const [isVerifying, setIsVerifying] = useState(false);
  const verifyingRef = useRef(false);

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [registrationToken, setRegistrationToken] = useState("");
  const [nombreCompleto, setNombreCompleto] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [role, setRole] = useState<Role | null>(null);
  const [documentoTipo, setDocumentoTipo] = useState<TipoDocumento | "">("");
  const [documentoNumero, setDocumentoNumero] = useState("");

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setTimeout(() => {
      setResendIn((seconds) => seconds - 1);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [resendIn]);

  function finish() {
    if (mode === "modal" && onSuccess) {
      onSuccess();
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  async function handleRequestOtp() {
    setError(null);
    setCode("");
    setShakeOtp(false);
    setIsPending(true);
    const result = await requestOtpAction(email);
    setIsPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setOtpResetKey((key) => key + 1);
    setResendIn(OTP_RESEND_COOLDOWN_SECONDS);
    setStep("otp");
  }

  async function handleVerifyOtp(nextCode: string) {
    if (nextCode.length !== 6 || verifyingRef.current) return;
    verifyingRef.current = true;
    setError(null);
    setIsPending(true);
    setIsVerifying(true);
    const result = await verifyOtpAction(email, nextCode);
    setIsPending(false);
    setIsVerifying(false);
    if (!result.ok) {
      verifyingRef.current = false;
      setCode("");
      setOtpResetKey((key) => key + 1);
      setShakeOtp(true);
      setError("El código es incorrecto");
      return;
    }
    if (result.data.status === "new_user") {
      setRegistrationToken(result.data.registrationToken);
      setStep("onboarding-name");
      return;
    }
    // Existing user: has_role is defensive/informational only today — every
    // OTP-created account already has a role by construction. A legacy
    // password-created account without one would land here too, but there's
    // no self-service "attach a role" endpoint yet (see docs/auth.md), so we
    // simply let them in rather than routing to an unsupported step.
    finish();
  }

  function handleContinueName() {
    setError(null);
    if (!nombreCompleto.trim()) {
      setError("El nombre completo es requerido");
      return;
    }
    if (!isValidColombianMobile(whatsapp)) {
      setError("Ingresa un celular colombiano de 10 dígitos");
      return;
    }
    setStep("onboarding-role");
  }

  async function handleCompleteOnboarding() {
    setError(null);
    if (!role) {
      setError("Elige una opción para continuar");
      return;
    }

    setIsPending(true);
    const result =
      role === "cliente"
        ? await registerClienteOtpAction({
            registration_token: registrationToken,
            nombre_completo: nombreCompleto,
            whatsapp: toE164ColombianMobile(whatsapp),
          })
        : await registerProfesionalOtpAction({
            registration_token: registrationToken,
            nombre_completo: nombreCompleto,
            whatsapp: toE164ColombianMobile(whatsapp),
            documento_tipo: documentoTipo as TipoDocumento,
            documento_numero: documentoNumero,
          });
    setIsPending(false);

    if (!result.ok) {
      setError(result.error);
      return;
    }
    finish();
  }

  const profesionalDocsIncomplete =
    role === "profesional" && (!documentoTipo || !documentoNumero.trim());
  const isWhatsappValid = isValidColombianMobile(whatsapp);
  const whatsappBlocking = whatsapp.length > 0 && !isWhatsappValid;
  const whatsappCompleteInvalid = whatsapp.length === 10 && !isWhatsappValid;

  return (
    <div className="flex w-full flex-col items-center gap-4 px-[4rem] py-10 ">
      <div className="flex flex-col items-center gap-1.5">
        <BuscaOficioMark size={60} />
      </div>

      {step === "email" && (
        <div className="flex w-full flex-col gap-5 text-center">
          <div>
            <h1 className="text-2xl font-bold text-azul dark:text-white">
              Bienvenido a <BuscaOficioWordmark size={23} />
            </h1>
            <p className="mt-5 font-extralight text-sm text-gray-600 dark:text-gray-400">
              {copy.subtitle}
            </p>
          </div>

          <div className="mx-auto flex w-[calc(100%-4rem)] flex-col gap-5">
            <Button
              type="button"
              variant="outline"
              disabled
              className="flex w-full rounded-2xl items-center justify-center gap-2 opacity-60"
              title="Próximamente"
            >
              <FaGoogle className="h-4 w-4" />
              Continuar con Google
              <span className="ml-1 bg-hueso-borde px-2 py-0.5 text-xs text-gray-500">
                Soons
              </span>
            </Button>

            <div className="flex w-full items-center gap-3 text-xs text-gray-400">
              <span className="h-px flex-1 bg-hueso-borde" />
              o
              <span className="h-px flex-1 bg-hueso-borde" />
            </div>

            <div className="flex w-full flex-col gap-2 text-left">
              {/* <Label htmlFor="email">Correo electrónico</Label> */}
              <Input
                id="email"
                type="email"
                placeholder="correo@ejemplo.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRequestOtp()}
              />
            </div>

            {error && <p className="text-sm text-red-500">{error}</p>}

            <Button
              type="button"
              className="w-full rounded-2xl bg-naranja hover:bg-naranja-hover"
              disabled={isPending || !email}
              onClick={handleRequestOtp}
            >
              {isPending ? "Enviando…" : "Continuar"}
            </Button>
          </div>

          <div className="flex flex-col gap-2 text-xs text-gray-400 dark:text-gray-500">
            <p>
              Al continuar, aceptas nuestros Términos y Política de Privacidad.
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {copy.toggleLead}{" "}
              <Link
                href={copy.toggleHref}
                prefetch
                className="font-medium text-naranja hover:text-naranja-hover hover:underline"
              >
                {copy.toggleAction}
              </Link>
            </p>
          </div>
        </div>
      )}

      {step === "otp" && (
        <div className="flex w-full flex-col gap-5 text-center">
          <div>
            <h1 className="text-2xl font-bold text-azul dark:text-white">
              Revisa tu correo
            </h1>
            <p className="mt-2 font-extralight text-sm text-gray-600 dark:text-gray-400">
              Hemos enviado un código al correo{" "}
              <span className="font-medium font-extralight text-azul dark:text-white">
                {email}
              </span>
            </p>
          </div>

          <div
            key={otpResetKey}
            className={`flex flex-col items-center gap-3 ${
              shakeOtp ? "animate-otp-shake" : ""
            }`}
            onAnimationEnd={() => setShakeOtp(false)}
          >
            <OtpCodeInput
              value={code}
              onChange={(next) => {
                setCode(next);
                if (error) setError(null);
              }}
              onComplete={handleVerifyOtp}
              disabled={isPending}
              invalid={Boolean(error)}
            />
            {error && (
              <p id="otp-error" role="alert" className="text-sm text-red-500">
                {error}
              </p>
            )}
          </div>

          {isVerifying && <p className="text-sm text-gray-400">Verificando…</p>}

          {!isVerifying && (
            <button
              type="button"
              className="text-sm font-extralight text-azul hover:underline dark:text-naranja-claro disabled:opacity-50"
              disabled={isPending || resendIn > 0}
              onClick={handleRequestOtp}
            >
              ¿No recibiste el código?{" "}
              <b>{resendIn > 0 ? `Reenviar en ${resendIn}s` : "Reenviar"}</b>
            </button>
          )}
        </div>
      )}

      {step === "onboarding-name" && (
        <div className="flex w-full flex-col gap-5 text-center">
          <div>
            <h1 className="text-2xl font-bold text-azul dark:text-white">
              Cuéntanos sobre ti
            </h1>
            <p className="mt-2 text-sm font-extralight  text-gray-600 dark:text-gray-400">
              Solo necesitamos un par de datos para crear tu cuenta
            </p>
          </div>

          <div className="mx-auto flex w-[calc(100%-4rem)] flex-col gap-5">
            <div className="flex flex-col gap-2 text-left">
              <Label htmlFor="nombre_completo">Nombre completo</Label>
              <Input
                id="nombre_completo"
                placeholder="Tu nombre completo"
                value={nombreCompleto}
                onChange={(e) => setNombreCompleto(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-2 text-left">
              <Label htmlFor="whatsapp">WhatsApp</Label>
              <div className="relative">
                <Input
                  id="whatsapp"
                  type="tel"
                  inputMode="numeric"
                  autoComplete="tel"
                  placeholder="300 000 0000"
                  value={whatsapp}
                  onChange={(e) =>
                    setWhatsapp(sanitizeColombianMobileInput(e.target.value))
                  }
                  className={cn(
                    isWhatsappValid && "pr-9",
                    whatsappCompleteInvalid && "border-red-500",
                  )}
                  aria-invalid={whatsappCompleteInvalid ? true : undefined}
                  aria-describedby={
                    isWhatsappValid
                      ? "whatsapp-valid"
                      : whatsappBlocking
                        ? "whatsapp-hint"
                        : undefined
                  }
                />
                {isWhatsappValid && (
                  <>
                    <Check
                      className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-verde"
                      aria-hidden
                    />
                    <span id="whatsapp-valid" className="sr-only">
                      Número de WhatsApp válido
                    </span>
                  </>
                )}
              </div>
              {whatsappCompleteInvalid && (
                <p
                  id="whatsapp-hint"
                  role="alert"
                  className="text-sm text-red-500"
                >
                  Ingresa un celular colombiano de 10 dígitos
                </p>
              )}
              {whatsappBlocking && !whatsappCompleteInvalid && (
                <p id="whatsapp-hint" className="text-sm text-gray-500">
                  Completa los 10 dígitos
                </p>
              )}
            </div>

            {error && <p className="text-sm text-red-500">{error}</p>}

            <Button
              type="button"
              className="w-full rounded-2xl bg-naranja hover:bg-naranja-hover"
              disabled={!isWhatsappValid}
              title={
                !isWhatsappValid
                  ? "Ingresa tu WhatsApp para continuar"
                  : undefined
              }
              onClick={handleContinueName}
            >
              Continuar
            </Button>
          </div>
        </div>
      )}

      {step === "onboarding-role" && (
        <div className="flex w-full flex-col gap-5 text-center">
          <div>
            <h1 className="text-2xl font-bold text-azul dark:text-white">
              ¿Qué te trae a BuscaOficio?
            </h1>
          </div>

          <div className="mx-auto flex w-[calc(100%-4rem)] flex-col gap-5">
            <div className="flex flex-col gap-3 text-left">
              <button
                type="button"
                onClick={() => setRole("cliente")}
                className={`rounded-lg border p-4 text-left transition-colors ${
                  role === "cliente"
                    ? "border-naranja bg-durazno-pale"
                    : "border-hueso-borde hover:border-naranja-claro"
                }`}
              >
                <span className="font-medium font-extralight text-azul dark:text-white">
                  Busco un profesional para un trabajo
                </span>
              </button>
              <button
                type="button"
                onClick={() => setRole("profesional")}
                className={`rounded-lg border p-4 text-left transition-colors ${
                  role === "profesional"
                    ? "border-naranja bg-durazno-pale"
                    : "border-hueso-borde hover:border-naranja-claro"
                }`}
              >
                <span className="font-medium font-extralight text-azul dark:text-white">
                  Ofrezco mis servicios como profesional
                </span>
              </button>
            </div>

            {role === "profesional" && (
              <div className="flex flex-col gap-4 text-left">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="documento_tipo">Tipo de documento</Label>
                  <Select
                    value={documentoTipo}
                    onValueChange={(v) => setDocumentoTipo(v as TipoDocumento)}
                  >
                    <SelectTrigger id="documento_tipo">
                      <SelectValue placeholder="Selecciona un tipo de documento" />
                    </SelectTrigger>
                    <SelectContent>
                      {DOCUMENTO_TIPOS.map((tipo) => (
                        <SelectItem key={tipo.value} value={tipo.value}>
                          {tipo.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="documento_numero">Número de documento</Label>
                  <Input
                    id="documento_numero"
                    placeholder="Número de documento"
                    value={documentoNumero}
                    onChange={(e) => setDocumentoNumero(e.target.value)}
                  />
                </div>
              </div>
            )}

            {error && <p className="text-sm text-red-500">{error}</p>}

            <Button
              type="button"
              className="w-full rounded-2xl bg-naranja hover:bg-naranja-hover"
              disabled={isPending || !role || profesionalDocsIncomplete}
              onClick={handleCompleteOnboarding}
            >
              {isPending ? "Creando cuenta…" : "Crear cuenta"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
