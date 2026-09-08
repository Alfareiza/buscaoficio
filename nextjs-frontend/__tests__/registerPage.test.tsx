import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import Page from "@/app/(auth)/register/page";

jest.mock("../components/auth/AuthCard", () => ({
  AuthCard: ({
    mode,
    intent,
    initialRegistrationToken,
    initialName,
  }: {
    mode: string;
    intent?: string;
    initialRegistrationToken?: string;
    initialName?: string;
  }) => (
    <div data-testid="auth-card">
      {mode}/{intent}/{initialRegistrationToken}/{initialName}
    </div>
  ),
}));

describe("Register Page", () => {
  it("renders the AuthCard in page mode with register intent", async () => {
    // Page is an async Server Component (searchParams is a Promise in the
    // App Router) — @testing-library/react can't render an async component
    // directly, so it's invoked and awaited manually, then the resolved
    // element is what gets rendered.
    const jsx = await Page({ searchParams: Promise.resolve({}) });
    render(jsx);

    expect(screen.getByTestId("auth-card")).toHaveTextContent("page/register");
  });

  it("passes registration_token/name from a Google callback redirect through to AuthCard", async () => {
    const jsx = await Page({
      searchParams: Promise.resolve({
        registration_token: "reg-token-abc",
        provider: "google",
        name: "Nueva Persona",
      }),
    });
    render(jsx);

    expect(screen.getByTestId("auth-card")).toHaveTextContent(
      "page/register/reg-token-abc/Nueva Persona",
    );
  });
});
