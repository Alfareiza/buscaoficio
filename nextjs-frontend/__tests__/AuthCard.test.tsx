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
  // AuthCard's resend-cooldown countdown uses a real 1s setTimeout loop
  // (60 ticks). Without fake timers, every test that reaches the OTP step
  // lets that countdown run in real wall-clock time in the background,
  // ballooning this file's run time by minutes. Nothing here asserts on the
  // countdown reaching a later value, just its initial "60s" state, so
  // fake timers (which waitFor auto-advances) are a safe, drop-in fix.
  jest.useFakeTimers();
  (useRouter as jest.Mock).mockReturnValue({ push, refresh });
});

afterEach(() => {
  jest.clearAllMocks();
  jest.useRealTimers();
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
      screen.getByRole("group", { name: /código de verificación/i }),
    ).toBeInTheDocument();
  });
}

function fillOtp(code: string) {
  fireEvent.change(screen.getByLabelText(/dígito 1 de 6/i), {
    target: { value: code },
  });
}

async function goToOnboardingName() {
  await goToOtpStep();
  (verifyOtpAction as jest.Mock).mockResolvedValue({
    ok: true,
    data: { status: "new_user", registrationToken: "reg-token-123" },
  });
  fillOtp("654321");
  await waitFor(() => {
    expect(screen.getByLabelText(/nombre completo/i)).toBeInTheDocument();
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
      screen.queryByRole("group", { name: /código de verificación/i }),
    ).not.toBeInTheDocument();
  });

  it("logs an existing user in and redirects to the dashboard", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });

    fillOtp("123456");

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
        screen.getByRole("group", { name: /código de verificación/i }),
      ).toBeInTheDocument(),
    );

    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });
    fillOtp("123456");

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });

  it("routes a brand-new email to onboarding and creates a cliente account", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "new_user", registrationToken: "reg-token-123" },
    });

    fillOtp("654321");

    await waitFor(() => {
      expect(screen.getByLabelText(/nombre completo/i)).toBeInTheDocument();
    });

    // Required field: continuing without a WhatsApp number leaves the button
    // disabled and does not advance to the role step.
    expect(screen.getByRole("button", { name: "Continuar" })).toBeDisabled();
    expect(
      screen.queryByText(/busco un profesional para un trabajo/i),
    ).not.toBeInTheDocument();

    // Required field: with a valid WhatsApp but an empty name, continuing
    // shows an error and still does not advance to the role step.
    fireEvent.change(screen.getByLabelText(/whatsapp/i), {
      target: { value: "3001234567" },
    });
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
        whatsapp: "+573001234567",
      });
    });
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("strips +57 from WhatsApp, shows a check when valid, and sends E.164 on register", async () => {
    await goToOnboardingName();

    const whatsapp = screen.getByLabelText(/whatsapp/i);
    fireEvent.change(whatsapp, { target: { value: "+57 300 123 4567" } });
    expect(whatsapp).toHaveValue("3001234567");
    expect(screen.getByText("Número de WhatsApp válido")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/nombre completo/i), {
      target: { value: "Ana Pérez" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    await waitFor(() => {
      expect(
        screen.getByText(/busco un profesional para un trabajo/i),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/busco un profesional para un trabajo/i));
    (registerClienteOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });
    fireEvent.click(screen.getByRole("button", { name: /crear cuenta/i }));

    await waitFor(() => {
      expect(registerClienteOtpAction).toHaveBeenCalledWith({
        registration_token: "reg-token-123",
        nombre_completo: "Ana Pérez",
        whatsapp: "+573001234567",
      });
    });
  });

  it("blocks continue when WhatsApp is filled but not a Colombian mobile", async () => {
    await goToOnboardingName();

    fireEvent.change(screen.getByLabelText(/nombre completo/i), {
      target: { value: "Ana Pérez" },
    });
    fireEvent.change(screen.getByLabelText(/whatsapp/i), {
      target: { value: "2001234567" },
    });
    expect(
      screen.queryByText("Número de WhatsApp válido"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Ingresa un celular colombiano de 10 dígitos"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continuar" })).toBeDisabled();
  });

  it("disables Continuar and hints to finish an incomplete WhatsApp number", async () => {
    await goToOnboardingName();

    fireEvent.change(screen.getByLabelText(/nombre completo/i), {
      target: { value: "Ana Pérez" },
    });
    fireEvent.change(screen.getByLabelText(/whatsapp/i), {
      target: { value: "300123" },
    });

    expect(screen.getByText("Completa los 10 dígitos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continuar" })).toBeDisabled();
  });

  it("disables Continuar when WhatsApp is left empty", async () => {
    await goToOnboardingName();

    fireEvent.change(screen.getByLabelText(/nombre completo/i), {
      target: { value: "Ana Pérez" },
    });

    expect(screen.getByRole("button", { name: "Continuar" })).toBeDisabled();
  });

  it("keeps the create-account button disabled for a profesional until the document fields are filled", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "new_user", registrationToken: "reg-token-123" },
    });
    fillOtp("654321");
    await waitFor(() => screen.getByLabelText(/nombre completo/i));
    fireEvent.change(screen.getByLabelText(/nombre completo/i), {
      target: { value: "Ana Pérez" },
    });
    fireEvent.change(screen.getByLabelText(/whatsapp/i), {
      target: { value: "3001234567" },
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

  it("does not show a Continuar button on the code step and verifies as soon as six digits are entered", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });

    expect(
      screen.queryByRole("button", { name: "Continuar" }),
    ).not.toBeInTheDocument();

    fillOtp("123456");

    await waitFor(() => {
      expect(verifyOtpAction).toHaveBeenCalledWith(
        "test@example.com",
        "123456",
      );
    });
  });

  it("shows El código es incorrecto, clears the boxes, and stays on the code step when verification fails", async () => {
    await goToOtpStep();
    (verifyOtpAction as jest.Mock).mockResolvedValue({
      ok: false,
      error: "Código inválido o expirado",
    });

    fillOtp("000000");

    await waitFor(() => {
      expect(screen.getByText("El código es incorrecto")).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/dígito 1 de 6/i)).toHaveValue("");
    expect(screen.getByLabelText(/dígito 6 de 6/i)).toHaveValue("");
    expect(push).not.toHaveBeenCalled();
  });

  it("moves focus to the next box after a digit is entered", async () => {
    await goToOtpStep();

    fireEvent.change(screen.getByLabelText(/dígito 1 de 6/i), {
      target: { value: "4" },
    });

    expect(screen.getByLabelText(/dígito 2 de 6/i)).toHaveFocus();
    expect(screen.getByLabelText(/dígito 1 de 6/i)).toHaveClass("bg-gray-100");
  });

  it("disables Reenviar during the resend cooldown after a code is sent", async () => {
    // First successful /otp/request starts a 60s frontend timer that matches
    // OtpManager.RESEND_COOLDOWN_SECONDS. A click inside that window still
    // gets HTTP 202 (anti-enumeration) but the backend sends no email — so
    // the button must stay disabled and show the remaining seconds instead
    // of looking like a successful resend.
    await goToOtpStep();

    const resend = screen.getByRole("button", { name: /reenviar/i });
    expect(resend).toBeDisabled();
    expect(resend).toHaveTextContent(/reenviar en 60s/i);
  });

  it("hides Reenviar and shows Verificando while the code is being checked", async () => {
    await goToOtpStep();
    let resolveVerify: (value: {
      ok: true;
      data: { status: "existing_user"; hasRole: boolean };
    }) => void = () => {};
    (verifyOtpAction as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveVerify = resolve;
        }),
    );

    fillOtp("123456");

    await waitFor(() => {
      expect(screen.getByText("Verificando…")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /reenviar/i }),
    ).not.toBeInTheDocument();

    resolveVerify({
      ok: true,
      data: { status: "existing_user", hasRole: true },
    });
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/dashboard");
    });
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
