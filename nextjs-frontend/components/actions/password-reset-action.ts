"use server";

// Dormant since 2026-08-18 — BuscaOficio moved to passwordless (email OTP)
// login. Kept in case password-based login returns as a fallback; not
// called from any linked UI (see /login's AuthCard for the current flow).

import * as Sentry from "@sentry/nextjs";

import { resetForgotPassword, resetResetPassword } from "@/app/clientService";
import { redirect } from "next/navigation";
import { passwordResetConfirmSchema } from "@/lib/definitions";
import { getErrorMessage } from "@/lib/utils";

export async function passwordReset(prevState: unknown, formData: FormData) {
  const input = {
    body: {
      email: formData.get("email") as string,
    },
  };

  try {
    const { error } = await resetForgotPassword(input);
    if (error) {
      return { server_validation_error: getErrorMessage(error) };
    }
    return { message: "Password reset instructions sent to your email." };
  } catch (error) {
    Sentry.captureException(error);
    Sentry.logger.error("Password reset error", {
      reason: error instanceof Error ? error.message : "Unknown error",
    });
    return {
      server_error: "An unexpected error occurred. Please try again later.",
    };
  }
}

export async function passwordResetConfirm(
  prevState: unknown,
  formData: FormData,
) {
  const validatedFields = passwordResetConfirmSchema.safeParse({
    token: formData.get("resetToken") as string,
    password: formData.get("password") as string,
    passwordConfirm: formData.get("passwordConfirm") as string,
  });

  if (!validatedFields.success) {
    return {
      errors: validatedFields.error.flatten().fieldErrors,
    };
  }

  const { token, password } = validatedFields.data;
  const input = {
    body: {
      token,
      password,
    },
  };
  try {
    const { error } = await resetResetPassword(input);
    if (error) {
      return { server_validation_error: getErrorMessage(error) };
    }
    redirect(`/login`);
  } catch (error) {
    Sentry.captureException(error);
    Sentry.logger.error("Password reset confirmation error", {
      reason: error instanceof Error ? error.message : "Unknown error",
    });
    return {
      server_error: "An unexpected error occurred. Please try again later.",
    };
  }
}
