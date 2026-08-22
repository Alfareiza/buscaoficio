import { AuthCard } from "@/components/auth/AuthCard";

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

  return (
    <AuthCard
      mode="page"
      intent="register"
      googleAuthorizeUrl={`${process.env.API_BASE_URL}/api/v1/auth/google/authorize`}
      initialRegistrationToken={registrationToken}
      initialName={name}
    />
  );
}
