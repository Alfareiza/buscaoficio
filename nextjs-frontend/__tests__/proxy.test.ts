/**
 * @jest-environment node
 */
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";
import { usersCurrentUser } from "@/app/clientService";

jest.mock("../app/clientService", () => ({
  usersCurrentUser: jest.fn(),
}));

function makeJwt(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256" })).toString(
    "base64url",
  );
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.signature`;
}

function makeRequest(cookiePairs: Record<string, string>): NextRequest {
  const cookieHeader = Object.entries(cookiePairs)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  return new NextRequest("https://frontend.test/dashboard", {
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
}

function mockFetchResponse(options: {
  ok: boolean;
  accessToken?: string;
  setCookies?: string[];
}) {
  return {
    ok: options.ok,
    json: async () => ({ access_token: options.accessToken }),
    headers: {
      getSetCookie: () => options.setCookies ?? [],
    },
  } as unknown as Response;
}

const NOT_NEAR_EXPIRY = Math.floor(Date.now() / 1000) + 60 * 60; // 1 hour out
const NEAR_EXPIRY = Math.floor(Date.now() / 1000) + 30; // 30s out — inside the buffer

describe("proxy middleware", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    process.env.API_BASE_URL = "https://backend.test";
  });

  it("redirects to /login when there is no access token", async () => {
    const request = makeRequest({});

    const response = await proxy(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://frontend.test/login",
    );
  });

  it("passes through when the token is valid and not near expiry", async () => {
    const token = makeJwt({ sub: "u1", exp: NOT_NEAR_EXPIRY });
    (usersCurrentUser as jest.Mock).mockResolvedValue({ error: undefined });
    const request = makeRequest({ accessToken: token });

    const response = await proxy(request);

    expect(usersCurrentUser).toHaveBeenCalledWith({
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.headers.get("location")).toBeNull();
  });

  it("redirects to /login and clears cookies when the token is invalid", async () => {
    const token = makeJwt({ sub: "u1", exp: NOT_NEAR_EXPIRY });
    (usersCurrentUser as jest.Mock).mockResolvedValue({
      error: { detail: "unauthorized" },
    });
    const request = makeRequest({ accessToken: token });

    const response = await proxy(request);

    expect(response.headers.get("location")).toBe(
      "https://frontend.test/login",
    );
  });

  it("refreshes the token when near expiry and forwards new cookies", async () => {
    const oldToken = makeJwt({ sub: "u1", exp: NEAR_EXPIRY });
    const newToken = makeJwt({ sub: "u1", exp: NOT_NEAR_EXPIRY });

    global.fetch = jest.fn().mockResolvedValue(
      mockFetchResponse({
        ok: true,
        accessToken: newToken,
        setCookies: [
          "refreshToken=new-refresh; HttpOnly; Max-Age=2592000; Path=/api/v1/auth/jwt/refresh; SameSite=strict; Secure",
          "fingerprintToken=new-fingerprint; HttpOnly; Max-Age=2592000; Path=/api/v1/auth/jwt/refresh; SameSite=strict; Secure",
        ],
      }),
    );
    (usersCurrentUser as jest.Mock).mockResolvedValue({ error: undefined });

    const request = makeRequest({
      accessToken: oldToken,
      refreshToken: "old-refresh",
      fingerprintToken: "old-fingerprint",
    });

    const response = await proxy(request);

    expect(global.fetch).toHaveBeenCalledWith(
      "https://backend.test/api/v1/auth/jwt/refresh",
      expect.objectContaining({
        method: "POST",
        headers: {
          Cookie: "refreshToken=old-refresh; fingerprintToken=old-fingerprint",
        },
      }),
    );
    expect(usersCurrentUser).toHaveBeenCalledWith({
      headers: { Authorization: `Bearer ${newToken}` },
    });
    expect(response.cookies.get("accessToken")?.value).toBe(newToken);
    expect(response.cookies.get("refreshToken")?.value).toBe("new-refresh");
    expect(response.cookies.get("fingerprintToken")?.value).toBe(
      "new-fingerprint",
    );
  });

  it("redirects to /login when near expiry but refresh/fingerprint cookies are missing", async () => {
    const oldToken = makeJwt({ sub: "u1", exp: NEAR_EXPIRY });
    global.fetch = jest.fn();

    const request = makeRequest({ accessToken: oldToken });

    const response = await proxy(request);

    expect(global.fetch).not.toHaveBeenCalled();
    expect(response.headers.get("location")).toBe(
      "https://frontend.test/login",
    );
  });

  it("redirects to /login and clears cookies when the refresh call is rejected", async () => {
    const oldToken = makeJwt({ sub: "u1", exp: NEAR_EXPIRY });
    global.fetch = jest
      .fn()
      .mockResolvedValue(mockFetchResponse({ ok: false }));

    const request = makeRequest({
      accessToken: oldToken,
      refreshToken: "old-refresh",
      fingerprintToken: "old-fingerprint",
    });

    const response = await proxy(request);

    expect(response.headers.get("location")).toBe(
      "https://frontend.test/login",
    );
    expect(usersCurrentUser).not.toHaveBeenCalled();
  });

  it("treats an undecodable access token as needing refresh", async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValue(mockFetchResponse({ ok: false }));

    const request = makeRequest({
      accessToken: "not-a-real-jwt",
      refreshToken: "old-refresh",
      fingerprintToken: "old-fingerprint",
    });

    const response = await proxy(request);

    expect(global.fetch).toHaveBeenCalled();
    expect(response.headers.get("location")).toBe(
      "https://frontend.test/login",
    );
  });
});
