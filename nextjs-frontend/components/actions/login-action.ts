"use server";

import * as Sentry from "@sentry/nextjs";
import { cookies } from "next/headers";

import { authJwtLogin } from "@/app/clientService";
import { redirect } from "next/navigation";
import { forwardAuthCookies, setAccessTokenCookie } from "@/lib/auth-cookies";
import { loginSchema } from "@/lib/definitions";
import { getErrorMessage } from "@/lib/utils";

export async function login(prevState: unknown, formData: FormData) {
  const validatedFields = loginSchema.safeParse({
    username: formData.get("username") as string,
    password: formData.get("password") as string,
  });

  if (!validatedFields.success) {
    return {
      errors: validatedFields.error.flatten().fieldErrors,
    };
  }

  const { username, password } = validatedFields.data;

  const input = {
    body: {
      username,
      password,
    },
  };

  try {
    const result = await authJwtLogin(input);
    const { data, error } = result;
    if (error) {
      return { server_validation_error: getErrorMessage(error) };
    }
    const accessToken =
      data &&
      typeof data === "object" &&
      "access_token" in data &&
      typeof data.access_token === "string"
        ? data.access_token
        : null;
    if (!accessToken) {
      return { server_validation_error: "An unknown error occurred" };
    }
    const cookieStore = await cookies();
    setAccessTokenCookie(cookieStore, accessToken);
    forwardAuthCookies(
      result.headers?.["set-cookie"] as string[] | undefined,
      cookieStore,
    );
  } catch (error) {
    Sentry.captureException(error);
    Sentry.logger.error("Login error", {
      reason: error instanceof Error ? error.message : "Unknown error",
    });
    return {
      server_error: "An unexpected error occurred. Please try again later.",
    };
  }
  redirect("/dashboard");
}
