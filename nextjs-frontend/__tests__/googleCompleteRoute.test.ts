/** @jest-environment node */
// next/server's NextRequest needs the Request/Response web APIs, which jsdom
// lacks — same reason proxy.test.ts pins the node environment.

import { NextRequest } from "next/server";
import * as Sentry from "@sentry/nextjs";

import { GET } from "@/app/api/auth/google/complete/route";
import { authGoogleSession } from "@/app/clientService";

jest.mock("../app/clientService", () => ({
  authGoogleSession: jest.fn(),
}));

jest.mock("@sentry/nextjs", () => ({
  logger: { info: jest.fn(), warn: jest.fn() },
  captureException: jest.fn(),
}));

function makeRequest(query = "") {
  return new NextRequest(
    `http://localhost:3000/api/auth/google/complete${query}`,
  );
}

const SESSION_RESPONSE = {
  data: {
    access_token: "the-access-token",
    status: "existing_user",
    has_role: true,
    nombre_completo: "Alfonso Areiza",
    email: "alfonso@example.com",
    picture: "https://lh3.googleusercontent.com/a/pic.jpg",
  },
  error: undefined,
  headers: {
    "set-cookie": [
      "refreshToken=r1; HttpOnly; Max-Age=2592000; Path=/api/v1/auth/jwt/refresh",
      "fingerprintToken=f1; HttpOnly; Max-Age=2592000; Path=/api/v1/auth/jwt/refresh",
    ],
  },
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("GET /api/auth/google/complete", () => {
  it("redirects straight to /dashboard — no intermediate page", async () => {
    (authGoogleSession as jest.Mock).mockResolvedValue(SESSION_RESPONSE);

    const response = await GET(makeRequest("?google_session_token=tok"));

    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/dashboard",
    );
  });

  it("sets the session cookies with SameSite=lax so they survive Google's cross-site redirect", async () => {
    (authGoogleSession as jest.Mock).mockResolvedValue(SESSION_RESPONSE);

    const response = await GET(makeRequest("?google_session_token=tok"));

    // Regression guard: with sameSite "strict" the browser withholds these
    // on the Google → backend → here → /dashboard chain (the chain starts
    // cross-site), proxy.ts sees no accessToken, and the user is bounced
    // back to /login on every attempt — an endless login loop.
    for (const name of ["accessToken", "refreshToken", "fingerprintToken"]) {
      const cookie = response.cookies.get(name);
      expect(cookie).toBeDefined();
      expect(cookie?.sameSite).toBe("lax");
    }
    expect(response.cookies.get("accessToken")?.value).toBe("the-access-token");
  });

  it("remembers the Google identity for /login's Continuar como card", async () => {
    (authGoogleSession as jest.Mock).mockResolvedValue(SESSION_RESPONSE);

    const response = await GET(makeRequest("?google_session_token=tok"));

    const raw = response.cookies.get("lastGoogleIdentity")?.value;
    expect(raw).toBeDefined();
    const identity = JSON.parse(
      Buffer.from(decodeURIComponent(raw as string), "base64").toString("utf8"),
    );
    expect(identity).toEqual({
      name: "Alfonso Areiza",
      email: "alfonso@example.com",
      picture: "https://lh3.googleusercontent.com/a/pic.jpg",
    });
  });

  it("redirects to /login with an error when the token is missing", async () => {
    const response = await GET(makeRequest());

    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login?error=google_auth_failed",
    );
    expect(authGoogleSession).not.toHaveBeenCalled();
    expect(Sentry.logger.warn).toHaveBeenCalledWith(
      "Google Sign-In complete route hit with no google_session_token",
    );
  });

  it("redirects to /login with an error when the backend rejects the token", async () => {
    const backendError = { detail: "google_session_token inválido o expirado" };
    (authGoogleSession as jest.Mock).mockResolvedValue({
      data: undefined,
      error: backendError,
      headers: {},
    });

    const response = await GET(makeRequest("?google_session_token=expired"));

    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login?error=google_auth_failed",
    );
    expect(Sentry.logger.warn).toHaveBeenCalledWith(
      "Google Sign-In session exchange rejected by backend",
      { error: backendError },
    );
  });

  it("redirects to /login with an error when the backend call throws", async () => {
    (authGoogleSession as jest.Mock).mockRejectedValue(new Error("network"));

    const response = await GET(makeRequest("?google_session_token=tok"));

    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login?error=google_auth_failed",
    );
  });
});
