const REFRESH_COOKIE_NAMES = ["refreshToken", "fingerprintToken"] as const;

/**
 * Structural type covering both `next/headers`' `cookies()` return value
 * (used in Server Actions) and `NextResponse.cookies` (used in
 * `proxy.ts`/middleware) — the two places these helpers get called from.
 * Matched structurally instead of imported so this file doesn't need to
 * pick one runtime's cookie type over the other's.
 */
interface CookieWriter {
  set(
    name: string,
    value: string,
    options?: {
      httpOnly?: boolean;
      secure?: boolean;
      sameSite?: "strict" | "lax" | "none";
      path?: string;
      maxAge?: number;
    },
  ): unknown;
  delete(name: string): unknown;
}

/**
 * Parses a single raw `Set-Cookie` header string into name/value/maxAge.
 * We only need the attributes we actually act on (Max-Age) — httpOnly,
 * secure, sameSite and path are re-applied explicitly by the caller rather
 * than trusted from the backend's cookie, since the frontend cookie is set
 * for a different origin (the Next.js server, not FastAPI).
 */
function parseSetCookieHeader(
  raw: string,
): { name: string; value: string; maxAge?: number } | null {
  const [pair, ...attributes] = raw.split(";").map((part) => part.trim());
  const separatorIndex = pair.indexOf("=");
  if (separatorIndex === -1) {
    return null;
  }

  const name = pair.slice(0, separatorIndex);
  const value = pair.slice(separatorIndex + 1);

  const maxAgeAttribute = attributes.find((attr) =>
    attr.toLowerCase().startsWith("max-age="),
  );
  const maxAge = maxAgeAttribute
    ? Number(maxAgeAttribute.split("=")[1])
    : undefined;

  return { name, value, maxAge };
}

/**
 * Re-applies the refresh/fingerprint cookies from a backend server-to-server
 * response onto the Next.js server's own response, so they reach the
 * browser. Server-to-server calls to FastAPI never expose Set-Cookie
 * headers to the browser directly — the Next.js server has to forward them
 * itself.
 */
export function forwardAuthCookies(
  setCookieHeaders: string[] | undefined,
  cookieStore: CookieWriter,
): void {
  if (!setCookieHeaders) {
    return;
  }

  for (const raw of setCookieHeaders) {
    const parsed = parseSetCookieHeader(raw);
    if (!parsed || !REFRESH_COOKIE_NAMES.includes(parsed.name as never)) {
      continue;
    }

    cookieStore.set(parsed.name, parsed.value, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: parsed.maxAge,
    });
  }
}

/** Sets the access token cookie with the flags it should always carry. */
export function setAccessTokenCookie(
  cookieStore: CookieWriter,
  accessToken: string,
): void {
  cookieStore.set("accessToken", accessToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
  });
}

/** Clears all auth cookies the frontend owns, including the raw JWT. */
export function clearAuthCookies(cookieStore: CookieWriter): void {
  cookieStore.delete("accessToken");
  for (const name of REFRESH_COOKIE_NAMES) {
    cookieStore.delete(name);
  }
}

/**
 * Decodes a JWT's `exp` claim without verifying the signature — safe here
 * because we only use it to schedule a refresh, never to authorize
 * anything. Returns the expiry as epoch milliseconds, or null if the token
 * is malformed.
 */
export function decodeJwtExpiryMs(token: string): number | null {
  const payloadSegment = token.split(".")[1];
  if (!payloadSegment) {
    return null;
  }

  try {
    const base64 = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64);
    const payload = JSON.parse(json) as { exp?: number };
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}
