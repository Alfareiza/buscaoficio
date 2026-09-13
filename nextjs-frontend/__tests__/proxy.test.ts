/**
 * @jest-environment node
 */
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

function makeJwt(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256" })).toString(
    "base64url",
  );
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.signature`;
}

function makeRequest(
  cookiePairs: Record<string, string>,
  extraHeaders?: Record<string, string>,
  url = "https://frontend.test/dashboard",
): NextRequest {
  const cookieHeader = Object.entries(cookiePairs)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  return new NextRequest(url, {
    headers: {
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
      ...extraHeaders,
    },
  });
}

function makeServerActionRequest(
  cookiePairs: Record<string, string>,
): NextRequest {
  return makeRequest(cookiePairs, { "next-action": "test-action-id" });
}

function makeBackendRequest(
  cookiePairs: Record<string, string>,
  extraHeaders?: Record<string, string>,
): NextRequest {
  return makeRequest(
    cookiePairs,
    extraHeaders,
    "https://frontend.test/api/backend/api/v1/catalogo/categorias",
  );
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

  it("passes through a valid token without calling FastAPI /me", async () => {
    global.fetch = jest.fn();
    const token = makeJwt({ sub: "u1", exp: NOT_NEAR_EXPIRY });
    const request = makeRequest({ accessToken: token });

    const response = await proxy(request);

    expect(global.fetch).not.toHaveBeenCalled();
    expect(response.headers.get("location")).toBeNull();
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

  it("does not 307 a Server Action when there is no access token", async () => {
    const request = makeServerActionRequest({});

    const response = await proxy(request);

    expect(response.status).not.toBe(307);
    expect(response.headers.get("location")).toBeNull();
  });

  it("does not 307 a Server Action when refresh fails", async () => {
    const oldToken = makeJwt({ sub: "u1", exp: NEAR_EXPIRY });
    global.fetch = jest
      .fn()
      .mockResolvedValue(mockFetchResponse({ ok: false }));

    const request = makeServerActionRequest({
      accessToken: oldToken,
      refreshToken: "old-refresh",
      fingerprintToken: "old-fingerprint",
    });

    const response = await proxy(request);

    expect(response.status).not.toBe(307);
    expect(response.headers.get("location")).toBeNull();
  });

  it("lets /api/backend through without a token so public catalog works", async () => {
    global.fetch = jest.fn();
    const request = makeBackendRequest({});

    const response = await proxy(request);

    expect(response.status).not.toBe(307);
    expect(response.headers.get("location")).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("refreshes on /api/backend when the token is near expiry without redirecting", async () => {
    const oldToken = makeJwt({ sub: "u1", exp: NEAR_EXPIRY });
    const newToken = makeJwt({ sub: "u1", exp: NOT_NEAR_EXPIRY });
    global.fetch = jest.fn().mockResolvedValue(
      mockFetchResponse({
        ok: true,
        accessToken: newToken,
        setCookies: [
          "refreshToken=new-refresh; HttpOnly; Max-Age=2592000",
          "fingerprintToken=new-fingerprint; HttpOnly; Max-Age=2592000",
        ],
      }),
    );

    const response = await proxy(
      makeBackendRequest({
        accessToken: oldToken,
        refreshToken: "old-refresh",
        fingerprintToken: "old-fingerprint",
      }),
    );

    expect(response.status).not.toBe(307);
    expect(response.cookies.get("accessToken")?.value).toBe(newToken);
  });

  it("clears cookies on /api/backend when refresh fails but does not 307", async () => {
    const oldToken = makeJwt({ sub: "u1", exp: NEAR_EXPIRY });
    global.fetch = jest
      .fn()
      .mockResolvedValue(mockFetchResponse({ ok: false }));

    const response = await proxy(
      makeBackendRequest({
        accessToken: oldToken,
        refreshToken: "old-refresh",
        fingerprintToken: "old-fingerprint",
      }),
    );

    expect(response.status).not.toBe(307);
    expect(response.headers.get("location")).toBeNull();
  });

});
