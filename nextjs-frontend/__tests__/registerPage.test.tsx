import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import Page from "@/app/(auth)/register/page";

jest.mock("../components/auth/AuthCard", () => ({
  AuthCard: ({ mode, intent }: { mode: string; intent?: string }) => (
    <div data-testid="auth-card">
      {mode}/{intent}
    </div>
  ),
}));

describe("Register Page", () => {
  it("renders the AuthCard in page mode with register intent", () => {
    render(<Page />);

    expect(screen.getByTestId("auth-card")).toHaveTextContent("page/register");
  });
});
