"use server";

import * as Sentry from "@sentry/nextjs";
import { redirect } from "next/navigation";

import { registerRegister } from "@/app/clientService";

import { registerSchema } from "@/lib/definitions";
import { getErrorMessage } from "@/lib/utils";

export async function register(prevState: unknown, formData: FormData) {
  const validatedFields = registerSchema.safeParse({
    email: formData.get("email") as string,
    password: formData.get("password") as string,
  });

  if (!validatedFields.success) {
    return {
      errors: validatedFields.error.flatten().fieldErrors,
    };
  }

  const { email, password } = validatedFields.data;

  const input = {
    body: {
      email,
      password,
    },
  };
  try {
    const { error } = await registerRegister(input);
    if (error) {
      return { server_validation_error: getErrorMessage(error) };
    }
  } catch (error) {
    Sentry.captureException(error);
    Sentry.logger.error("Registration error", {
      reason: error instanceof Error ? error.message : "Unknown error",
    });
    return {
      server_error: "An unexpected error occurred. Please try again later.",
    };
  }
  redirect(`/login`);
}
