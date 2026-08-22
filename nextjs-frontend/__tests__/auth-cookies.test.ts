import {
  clearAuthCookies,
  decodeJwtExpiryMs,
  forwardAuthCookies,
  setAccessTokenCookie,
} from "@/lib/auth-cookies";

function makeCookieWriter() {
  return { set: jest.fn(), delete: jest.fn() };
}

function makeJwt(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256" })).toString(
    "base64url",
  );
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.signature`;
}

describe("decodeJwtExpiryMs", () => {
  it("returns the exp claim converted to epoch milliseconds", () => {
    const token = makeJwt({ sub: "user-1", exp: 1700000000 });
    expect(decodeJwtExpiryMs(token)).toBe(1700000000 * 1000);
  });

  it("returns null for a malformed token", () => {
    expect(decodeJwtExpiryMs("not-a-jwt")).toBeNull();
  });

  it("returns null when the payload has no exp claim", () => {
    const token = makeJwt({ sub: "user-1" });
    expect(decodeJwtExpiryMs(token)).toBeNull();
  });
});

describe("forwardAuthCookies", () => {
  it("applies refreshToken and fingerprintToken with maxAge parsed from Max-Age", () => {
    const cookieStore = makeCookieWriter();

    forwardAuthCookies(
      [
        "refreshToken=abc123; HttpOnly; Max-Age=2592000; Path=/api/v1/auth/jwt/refresh; SameSite=strict; Secure",
        "fingerprintToken=def456; HttpOnly; Max-Age=2592000; Path=/api/v1/auth/jwt/refresh; SameSite=strict; Secure",
      ],
      cookieStore,
    );

    expect(cookieStore.set).toHaveBeenCalledWith(
      "refreshToken",
      "abc123",
      expect.objectContaining({
        httpOnly: true,
        // lax, not strict — see AUTH_COOKIE_SAME_SITE in lib/auth-cookies.ts.
        // Strict withholds these on Google Sign-In's cross-site-initiated
        // redirect back into /dashboard, producing a login loop.
        sameSite: "lax",
        path: "/",
        maxAge: 2592000,
      }),
    );
    expect(cookieStore.set).toHaveBeenCalledWith(
      "fingerprintToken",
      "def456",
      expect.objectContaining({ maxAge: 2592000 }),
    );
  });

  it("ignores cookies that are not refreshToken/fingerprintToken", () => {
    const cookieStore = makeCookieWriter();

    forwardAuthCookies(["someOtherCookie=value; Path=/"], cookieStore);

    expect(cookieStore.set).not.toHaveBeenCalled();
  });

  it("does nothing when there are no Set-Cookie headers", () => {
    const cookieStore = makeCookieWriter();

    forwardAuthCookies(undefined, cookieStore);

    expect(cookieStore.set).not.toHaveBeenCalled();
  });
});

describe("clearAuthCookies", () => {
  it("deletes accessToken, refreshToken, and fingerprintToken", () => {
    const cookieStore = makeCookieWriter();

    clearAuthCookies(cookieStore);

    expect(cookieStore.delete).toHaveBeenCalledWith("accessToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("refreshToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("fingerprintToken");
  });
});

describe("setAccessTokenCookie", () => {
  it("sets accessToken with httpOnly/sameSite/path flags", () => {
    const cookieStore = makeCookieWriter();

    setAccessTokenCookie(cookieStore, "the-token");

    expect(cookieStore.set).toHaveBeenCalledWith(
      "accessToken",
      "the-token",
      expect.objectContaining({
        httpOnly: true,
        // lax is load-bearing for the Google Sign-In return trip — see the
        // forwardAuthCookies test above and AUTH_COOKIE_SAME_SITE.
        sameSite: "lax",
        path: "/",
      }),
    );
  });
});
