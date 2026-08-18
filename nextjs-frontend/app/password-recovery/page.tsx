"use client";

// Dormant since 2026-08-18 — BuscaOficio moved to passwordless (email OTP)
// login. Kept in case password-based login returns as a fallback; not
// linked from any UI (see /login's AuthCard for the current flow).

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { passwordReset } from "@/components/actions/password-reset-action";
import { useActionState } from "react";
import { SubmitButton } from "@/components/ui/submitButton";
import Link from "next/link";
import { FormError } from "@/components/ui/FormError";
import { BuscaOficioLogo } from "@/components/ui/BuscaOficioLogo";

export default function Page() {
  const [state, dispatch] = useActionState(passwordReset, undefined);

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 px-4 gap-6">
      <BuscaOficioLogo width={100} height={100} href="/" />
      <form action={dispatch}>
        <Card className="w-full max-w-sm rounded-lg shadow-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800">
          <CardHeader className="flex flex-col items-center justify-center">
            <CardTitle className="text-2xl font-semibold text-gray-800 dark:text-white">
              Recuperación de Contraseña
            </CardTitle>
            <CardDescription className="text-sm text-gray-600 dark:text-gray-400">
              Introduce tu correo electrónico para recibir instrucciones para
              restablecer tu contraseña.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 p-6">
            <div className="grid gap-3">
              <Label
                htmlFor="email"
                className="text-gray-700 dark:text-gray-300"
              >
                Email
              </Label>
              <Input
                id="email"
                name="email"
                type="email"
                placeholder="m@example.com"
                required
                className="border-gray-300 dark:border-gray-600"
              />
            </div>
            <SubmitButton text="Send" />
            <FormError state={state} />
            <div className="mt-2 text-sm text-center text-blue-500">
              {state?.message && <p>{state.message}</p>}
            </div>
            <div className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">
              <Link
                href="/login"
                className="text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-500"
              >
                Back to login
              </Link>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
