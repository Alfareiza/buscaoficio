"use client";

// Dormant since 2026-08-18 — BuscaOficio moved to passwordless (email OTP)
// login. Kept in case password-based login returns as a fallback; not
// linked from any UI (see /login's AuthCard for the current flow).

import { useActionState } from "react";
import { notFound, useSearchParams } from "next/navigation";
import { passwordResetConfirm } from "@/components/actions/password-reset-action";
import { SubmitButton } from "@/components/ui/submitButton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Suspense } from "react";
import { FieldError, FormError } from "@/components/ui/FormError";
import { BuscaOficioLogo } from "@/components/ui/BuscaOficioLogo";

function ResetPasswordForm() {
  const [state, dispatch] = useActionState(passwordResetConfirm, undefined);
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  if (!token) {
    notFound();
  }

  return (
    <form action={dispatch}>
      <Card className="w-full max-w-sm rounded-lg shadow-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800">
        <CardHeader className="flex flex-col items-center justify-center">
          <CardTitle className="text-2xl font-semibold text-gray-800 dark:text-white">
            Reset your Password
          </CardTitle>
          <CardDescription className="text-sm text-gray-600 dark:text-gray-400">
            Enter the new password and confirm it.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 p-6">
          <div className="grid gap-2">
            <Label htmlFor="password" className="text-gray-700 dark:text-gray-300">Password</Label>
            <Input id="password" name="password" type="password" required className="border-gray-300 dark:border-gray-600" />
          </div>
          <FieldError state={state} field="password" />
          <div className="grid gap-2">
            <Label htmlFor="passwordConfirm" className="text-gray-700 dark:text-gray-300">Password Confirm</Label>
            <Input
              id="passwordConfirm"
              name="passwordConfirm"
              type="password"
              required
              className="border-gray-300 dark:border-gray-600"
            />
          </div>
          <FieldError state={state} field="passwordConfirm" />
          <input
            type="hidden"
            id="resetToken"
            name="resetToken"
            value={token}
            readOnly
          />
          <SubmitButton text={"Send"} />
          <FormError state={state} />
        </CardContent>
      </Card>
    </form>
  );
}

export default function Page() {
  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 px-4 gap-6">
      <BuscaOficioLogo width={100} height={100} href="/" />
      <Suspense fallback={<div>Loading reset form...</div>}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
