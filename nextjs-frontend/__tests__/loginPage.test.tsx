import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import Page from "@/app/(auth)/login/page";

jest.mock("../components/auth/AuthCard", () => ({
  AuthCard: ({ mode, intent }: { mode: string; intent?: string }) => (
    <div data-testid="auth-card">
      {mode}/{intent}
    </div>
  ),
}));

describe("Login Page", () => {
  it("renders the AuthCard in page mode with login intent", () => {
    render(<Page />);

    expect(screen.getByTestId("auth-card")).toHaveTextContent("page/login");
  });
});
