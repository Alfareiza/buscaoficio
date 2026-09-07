import { AuthCard } from "@/components/auth/AuthCard";

type PreviewStep =
  | "email"
  | "otp"
  | "onboarding-name"
  | "onboarding-role";

const PREVIEW_STEPS = new Set<PreviewStep>([
  "email",
  "otp",
  "onboarding-name",
  "onboarding-role",
]);

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const registrationToken =
    typeof params.registration_token === "string"
      ? params.registration_token
      : undefined;
  const name = typeof params.name === "string" ? params.name : undefined;
  // Local-only shortcut so a step can be opened without walking OTP.
  // Ignored in production builds.
  const previewStep =
    process.env.NODE_ENV !== "production" &&
    typeof params.preview_step === "string" &&
    PREVIEW_STEPS.has(params.preview_step as PreviewStep)
      ? (params.preview_step as PreviewStep)
      : undefined;

  return (
    <AuthCard
      mode="page"
      intent="register"
      googleAuthorizeUrl={`${process.env.API_BASE_URL}/api/v1/auth/google/authorize`}
      initialRegistrationToken={registrationToken}
      initialName={name}
      initialStep={previewStep}
    />
  );
}
