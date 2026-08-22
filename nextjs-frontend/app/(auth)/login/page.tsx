import { cookies } from "next/headers";

import { AuthCard } from "@/components/auth/AuthCard";
import {
  decodeGoogleIdentity,
  GOOGLE_IDENTITY_COOKIE,
} from "@/lib/google-identity-cookie";

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  google_auth_failed: "No pudimos iniciar sesión con Google. Intenta de nuevo.",
};

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const errorCode = typeof params.error === "string" ? params.error : undefined;

  // Read server-side so the "Continuar como {name}" card is in the very
  // first HTML — no client effect, no flash of the blank email form.
  const cookieStore = await cookies();
  const googleIdentity = decodeGoogleIdentity(
    cookieStore.get(GOOGLE_IDENTITY_COOKIE)?.value,
  );

  return (
    <AuthCard
      mode="page"
      intent="login"
      googleAuthorizeUrl={`${process.env.API_BASE_URL}/api/v1/auth/google/authorize`}
      initialError={errorCode ? GOOGLE_ERROR_MESSAGES[errorCode] : undefined}
      googleIdentity={googleIdentity}
    />
  );
}
