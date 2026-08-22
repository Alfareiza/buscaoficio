import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { cookies } from "next/headers";

import Page from "@/app/(auth)/login/page";
import { encodeGoogleIdentity } from "@/lib/google-identity-cookie";

jest.mock("next/headers", () => ({
  cookies: jest.fn(),
}));

jest.mock("../components/auth/AuthCard", () => ({
  AuthCard: ({
    mode,
    intent,
    initialError,
    googleIdentity,
  }: {
    mode: string;
    intent?: string;
    initialError?: string;
    googleIdentity?: { name: string; email: string; picture: string | null } | null;
  }) => (
    <div data-testid="auth-card">
      {mode}/{intent}/{initialError}/{googleIdentity?.name}/
      {googleIdentity?.email}/{googleIdentity?.picture}
    </div>
  ),
}));

function mockCookies(store: Record<string, string>) {
  (cookies as jest.Mock).mockResolvedValue({
    get: (name: string) =>
      name in store ? { name, value: store[name] } : undefined,
  });
}

describe("Login Page", () => {
  it("renders the AuthCard in page mode with login intent", async () => {
    mockCookies({});

    // Page is an async Server Component (searchParams is a Promise in the
    // App Router) — @testing-library/react can't render an async component
    // directly, so it's invoked and awaited manually, then the resolved
    // element is what gets rendered.
    const jsx = await Page({ searchParams: Promise.resolve({}) });
    render(jsx);

    expect(screen.getByTestId("auth-card")).toHaveTextContent("page/login");
  });

  it("maps a google_auth_failed error code to a Spanish error message", async () => {
    mockCookies({});

    const jsx = await Page({
      searchParams: Promise.resolve({ error: "google_auth_failed" }),
    });
    render(jsx);

    expect(screen.getByTestId("auth-card")).toHaveTextContent(
      "No pudimos iniciar sesión con Google. Intenta de nuevo.",
    );
  });

  it("passes the remembered Google identity from its cookie down to AuthCard", async () => {
    mockCookies({
      lastGoogleIdentity: encodeGoogleIdentity({
        name: "Alfonso",
        email: "alfonso@example.com",
        picture: "https://lh3.googleusercontent.com/a/pic.jpg",
      }),
    });

    const jsx = await Page({ searchParams: Promise.resolve({}) });
    render(jsx);

    const card = screen.getByTestId("auth-card");
    expect(card).toHaveTextContent("Alfonso");
    expect(card).toHaveTextContent("alfonso@example.com");
    expect(card).toHaveTextContent("https://lh3.googleusercontent.com/a/pic.jpg");
  });

  it("passes no identity when the cookie is malformed", async () => {
    mockCookies({ lastGoogleIdentity: "not-valid-base64-json" });

    const jsx = await Page({ searchParams: Promise.resolve({}) });
    render(jsx);

    expect(screen.getByTestId("auth-card")).toHaveTextContent("page/login///");
  });
});
