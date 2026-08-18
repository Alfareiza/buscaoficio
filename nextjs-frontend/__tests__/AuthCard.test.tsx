import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { useRouter } from "next/navigation";

import { AuthCard } from "@/components/auth/AuthCard";
import {
  requestOtpAction,
  verifyOtpAction,
  registerClienteOtpAction,
} from "@/components/actions/otp-auth-action";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("../components/actions/otp-auth-action", () => ({
  requestOtpAction: jest.fn(),
  verifyOtpAction: jest.fn(),
  registerClienteOtpAction: jest.fn(),
  registerProfesionalOtpAction: jest.fn(),
}));

const push = jest.fn();
const refresh = jest.fn();

beforeEach(() => {
  (useRouter as jest.Mock).mockReturnValue({ push, refresh });
});

afterEach(() => {
  jest.clearAllMocks();
});

async function goToOtpStep(email = "test@example.com") {
  (requestOtpAction as jest.Mock).mockResolvedValue({ ok: true, data: null });
  render(<AuthCard mode="page" />);

  fireEvent.change(screen.getByPlaceholderText("correo@ejemplo.com"), {
    target: { value: email },
  });
  fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

  await waitFor(() => {
    expect(
      screen.getByLabelText(/código de verificación/i),
    ).toBeInTheDocument();
  });
}

describe("AuthCard", () => {
  it("requests an OTP for the entered email and advances to the code step", async () => {
    await goToOtpStep("test@example.com");

    expect(requestOtpAction).toHaveBeenCalledWith("test@example.com");
  });

  it("shows an error and stays on the email step if the OTP request fails", async () => {
    (requestOtpAction as jest.Mock).mockResolvedValue({
      ok: false,
      error: "No pudimos enviar el código. Intenta de nuevo.",
    });

    render(<AuthCard mode="page" />);

    fireEvent.change(screen.getByPlaceholderText("correo@ejemplo.com"), {
      target: { value: "test@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => {
      expect(
        screen.getByText("No pudimos enviar el código. Intenta de nuevo."),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByLabelText(/código de verificación/i),
    ).not.toBeInTheDocument();
  });

  it("logs an existing user in and redirects to the dashboard", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });

    fireEvent.change(screen.getByLabelText(/código de verificación/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/dashboard");
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("calls onSuccess instead of navigating when rendered in modal mode", async () => {
    const onSuccess = jest.fn();
    (requestOtpAction as jest.Mock).mockResolvedValue({ ok: true, data: null });
    render(<AuthCard mode="modal" onSuccess={onSuccess} />);

    fireEvent.change(screen.getByPlaceholderText("correo@ejemplo.com"), {
      target: { value: "test@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    await waitFor(() =>
      expect(
        screen.getByLabelText(/código de verificación/i),
      ).toBeInTheDocument(),
    );

    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });
    fireEvent.change(screen.getByLabelText(/código de verificación/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });

  it("routes a brand-new email to onboarding and creates a cliente account", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "new_user", registrationToken: "reg-token-123" },
    });

    fireEvent.change(screen.getByLabelText(/código de verificación/i), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => {
      expect(screen.getByLabelText(/nombre completo/i)).toBeInTheDocument();
    });

    // Required field: continuing with an empty name shows an error and does
    // not advance to the role step.
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(
      screen.getByText("El nombre completo es requerido"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/nombre completo/i), {
      target: { value: "Ana Pérez" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => {
      expect(
        screen.getByText(/busco un profesional para un trabajo/i),
      ).toBeInTheDocument();
    });

    const createAccountButton = screen.getByRole("button", {
      name: /crear cuenta/i,
    });
    expect(createAccountButton).toBeDisabled();

    fireEvent.click(screen.getByText(/busco un profesional para un trabajo/i));
    expect(createAccountButton).toBeEnabled();

    (registerClienteOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });
    fireEvent.click(createAccountButton);

    await waitFor(() => {
      expect(registerClienteOtpAction).toHaveBeenCalledWith({
        registration_token: "reg-token-123",
        nombre_completo: "Ana Pérez",
        whatsapp: undefined,
      });
    });
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("keeps the create-account button disabled for a profesional until the document fields are filled", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "new_user", registrationToken: "reg-token-123" },
    });
    fireEvent.change(screen.getByLabelText(/código de verificación/i), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    await waitFor(() => screen.getByLabelText(/nombre completo/i));
    fireEvent.change(screen.getByLabelText(/nombre completo/i), {
      target: { value: "Ana Pérez" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    await waitFor(() =>
      screen.getByText(/ofrezco mis servicios como profesional/i),
    );

    fireEvent.click(
      screen.getByText(/ofrezco mis servicios como profesional/i),
    );

    expect(
      screen.getByRole("button", { name: /crear cuenta/i }),
    ).toBeDisabled();
  });

  it("shows the legal notice and a Registrarme link to /register by default (login intent)", () => {
    render(<AuthCard mode="page" />);

    expect(
      screen.getByText(/Al continuar, aceptas nuestros Términos/i),
    ).toBeInTheDocument();

    const link = screen.getByRole("link", { name: "Registrarme" });
    expect(link).toHaveAttribute("href", "/register");
    expect(screen.getByText("No tengo cuenta.")).toBeInTheDocument();
  });

  it("shows the register subtitle and an Iniciar Sesión link to /login for register intent", () => {
    render(<AuthCard mode="page" intent="register" />);

    expect(
      screen.getByText("Crea una cuenta y descubre lo que puedes encontrar"),
    ).toBeInTheDocument();

    const link = screen.getByRole("link", { name: "Iniciar Sesión" });
    expect(link).toHaveAttribute("href", "/login");
    expect(screen.getByText("Ya tengo una cuenta.")).toBeInTheDocument();
  });
});
