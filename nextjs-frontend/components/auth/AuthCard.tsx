"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FaGoogle } from "react-icons/fa";

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

type Step = "email" | "otp" | "onboarding-name" | "onboarding-role";
type Role = "cliente" | "profesional";

const DOCUMENTO_TIPOS: { value: TipoDocumento; label: string }[] = [
  { value: "CC", label: "Cédula de Ciudadanía" },
  { value: "CE", label: "Cédula de Extranjería" },
  { value: "TI", label: "Tarjeta de Identidad" },
  { value: "RC", label: "Registro Civil" },
  { value: "PA", label: "Pasaporte" },
  { value: "MS", label: "Menor sin Identificación" },
  { value: "PE", label: "Permiso Especial" },
  { value: "CN", label: "Certificado Nacido Vivo" },
  { value: "PT", label: "Permiso Temporal" },
  { value: "SC", label: "Salvo Conducto" },
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

export function AuthCard({ mode, intent = "login", onSuccess }: AuthCardProps) {
  const router = useRouter();
  const copy = INTENT_COPY[intent];

  const [step, setStep] = useState<Step>("email");
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [registrationToken, setRegistrationToken] = useState("");
  const [nombreCompleto, setNombreCompleto] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [role, setRole] = useState<Role | null>(null);
  const [documentoTipo, setDocumentoTipo] = useState<TipoDocumento | "">("");
  const [documentoNumero, setDocumentoNumero] = useState("");

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
    setIsPending(true);
    const result = await requestOtpAction(email);
    setIsPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setStep("otp");
  }

  async function handleVerifyOtp() {
    setError(null);
    setIsPending(true);
    const result = await verifyOtpAction(email, code);
    setIsPending(false);
    if (!result.ok) {
      setError(result.error);
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
            whatsapp: whatsapp || undefined,
          })
        : await registerProfesionalOtpAction({
            registration_token: registrationToken,
            nombre_completo: nombreCompleto,
            whatsapp: whatsapp || undefined,
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

            <Button
              type="button"
              variant="outline"
              disabled
              className="flex w-min items-center justify-center gap-2 opacity-60"
              title="Próximamente"
              >
              <FaGoogle className="h-4 w-4" />
              Continuar con Google
              <span className="ml-1 rounded-full bg-hueso-borde px-2 py-0.5 text-xs text-gray-500">
                Próximamente
              </span>
            </Button>

          <div className="flex items-center gap-3 text-xs text-gray-400">
            <span className="h-px flex-1 bg-hueso-borde" />
            o
            <span className="h-px flex-1 bg-hueso-borde" />
          </div>

          <div className="flex flex-col gap-2 text-left">
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
            className="w-full bg-naranja hover:bg-naranja-hover"
            disabled={isPending || !email}
            onClick={handleRequestOtp}
          >
            {isPending ? "Enviando…" : "Continuar"}
          </Button>

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
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              Ingresa el código de 6 dígitos que enviamos a{" "}
              <span className="font-medium text-azul dark:text-white">
                {email}
              </span>
            </p>
          </div>

          <div className="flex flex-col gap-2 text-left">
            <Label htmlFor="code">Código de verificación</Label>
            <Input
              id="code"
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              className="text-center text-lg tracking-[0.5em]"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              onKeyDown={(e) => e.key === "Enter" && handleVerifyOtp()}
            />
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <Button
            type="button"
            className="w-full bg-naranja hover:bg-naranja-hover"
            disabled={isPending || code.length !== 6}
            onClick={handleVerifyOtp}
          >
            {isPending ? "Verificando…" : "Continuar"}
          </Button>

          <button
            type="button"
            className="text-sm text-azul hover:underline dark:text-naranja-claro disabled:opacity-50"
            disabled={isPending}
            onClick={handleRequestOtp}
          >
            ¿No recibiste el código? Reenviar
          </button>
        </div>
      )}

      {step === "onboarding-name" && (
        <div className="flex w-full flex-col gap-5 text-center">
          <div>
            <h1 className="text-2xl font-bold text-azul dark:text-white">
              Cuéntanos sobre ti
            </h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              Solo necesitamos un par de datos para crear tu cuenta
            </p>
          </div>

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
            <Label htmlFor="whatsapp">WhatsApp (opcional)</Label>
            <Input
              id="whatsapp"
              placeholder="+57 300 000 0000"
              value={whatsapp}
              onChange={(e) => setWhatsapp(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <Button
            type="button"
            className="w-full bg-naranja hover:bg-naranja-hover"
            onClick={handleContinueName}
          >
            Continuar
          </Button>
        </div>
      )}

      {step === "onboarding-role" && (
        <div className="flex w-full flex-col gap-5 text-center">
          <div>
            <h1 className="text-2xl font-bold text-azul dark:text-white">
              ¿Qué te trae a BuscaOficio?
            </h1>
          </div>

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
              <span className="font-medium text-azul dark:text-white">
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
              <span className="font-medium text-azul dark:text-white">
                Ofrezco mis servicios como profesional
              </span>
            </button>
          </div>

          {role === "profesional" && (
            <div className="flex flex-col gap-4 text-left">
              <div className="flex flex-col gap-2">
                <Label htmlFor="documento_tipo">Tipo de documento</Label>
                <Select
                  value={documentoTipo || undefined}
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
            className="w-full bg-naranja hover:bg-naranja-hover"
            disabled={isPending || !role || profesionalDocsIncomplete}
            onClick={handleCompleteOnboarding}
          >
            {isPending ? "Creando cuenta…" : "Crear cuenta"}
          </Button>
        </div>
      )}
    </div>
  );
}
