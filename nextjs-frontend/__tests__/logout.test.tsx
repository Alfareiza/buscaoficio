/** @jest-environment node */
// next/server's NextRequest needs Request/Response, which jsdom lacks.

import { NextRequest, type NextResponse } from "next/server";

import { POST } from "@/app/api/auth/logout/route";
import { authJwtLogout } from "@/app/clientService";

jest.mock("../app/clientService", () => ({
  authJwtLogout: jest.fn(),
}));

function makeRequest(cookieHeader?: string) {
  return new NextRequest("http://localhost:3000/api/auth/logout", {
    method: "POST",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
}

function expectClearedAuthCookies(response: NextResponse) {
  for (const name of ["accessToken", "refreshToken", "fingerprintToken"]) {
    const cookie = response.cookies.get(name);
    expect(cookie).toBeDefined();
    expect(cookie?.value === "" || cookie?.maxAge === 0).toBe(true);
  }
}

beforeEach(() => {
  jest.clearAllMocks();
  delete process.env.FRONTEND_URL;
});

describe("POST /api/auth/logout", () => {
  it("revokes on the backend, clears auth cookies, and 303s to /login", async () => {
    (authJwtLogout as jest.Mock).mockResolvedValue({ error: undefined });

    const response = await POST(
      makeRequest("accessToken=some-token; refreshToken=r; fingerprintToken=f"),
    );

    expect(authJwtLogout).toHaveBeenCalledWith({
      headers: { Authorization: "Bearer some-token" },
    });
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login",
    );
    expectClearedAuthCookies(response);
  });

  it("clears cookies and redirects even when there is no access token", async () => {
    const response = await POST(makeRequest());

    expect(authJwtLogout).not.toHaveBeenCalled();
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login",
    );
    expectClearedAuthCookies(response);
  });

  it("clears cookies and redirects even when the backend logout call fails", async () => {
    (authJwtLogout as jest.Mock).mockResolvedValue({
      error: { detail: "unauthorized" },
    });

    const response = await POST(makeRequest("accessToken=stale-token"));

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login",
    );
    expectClearedAuthCookies(response);
  });

  it("clears cookies and redirects when the backend logout call throws", async () => {
    (authJwtLogout as jest.Mock).mockRejectedValue(new Error("network"));

    const response = await POST(makeRequest("accessToken=some-token"));

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/login",
    );
    expectClearedAuthCookies(response);
  });

  it("uses FRONTEND_URL for Location when set (Caddy / bind-address)", async () => {
    process.env.FRONTEND_URL = "https://app.buscaoficio.co";
    (authJwtLogout as jest.Mock).mockResolvedValue({ error: undefined });

    const response = await POST(makeRequest("accessToken=some-token"));

    expect(response.headers.get("location")).toBe(
      "https://app.buscaoficio.co/login",
    );
  });
});
