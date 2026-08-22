/** Remembers the last Google-signed-in user so /login can greet them with
 * "Continuar como {name}" (avatar + name + email) instead of a blank form.
 *
 * Stored as a plain cookie rather than localStorage so the /login Server
 * Component can read it during render — no client-side effect, no hydration
 * mismatch, and no flash of the blank form before the card appears.
 *
 * This is display-only data, never a credential: it holds nothing that can
 * authenticate anyone, and clicking the card still runs the full Google
 * OAuth flow. It deliberately OUTLIVES logout — a returning user should see
 * their own name whether their session expired or they signed out on
 * purpose. Nothing here is ever trusted server-side for authorization.
 */

const COOKIE_NAME = "lastGoogleIdentity";
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export interface GoogleIdentity {
  name: string;
  email: string;
  picture: string | null;
}

/** Structural writer type — same approach as lib/auth-cookies.ts, so these
 * work with both `next/headers`' cookies() (Server Actions) and
 * NextResponse.cookies (Route Handlers). */
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
}

function isGoogleIdentity(value: unknown): value is GoogleIdentity {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.name === "string" &&
    typeof v.email === "string" &&
    (typeof v.picture === "string" || v.picture === null)
  );
}

/** base64 keeps the cookie value ASCII-safe — names and emails can contain
 * accented characters, which a raw JSON cookie value can't carry. */
export function encodeGoogleIdentity(identity: GoogleIdentity): string {
  return Buffer.from(JSON.stringify(identity), "utf8").toString("base64");
}

export function decodeGoogleIdentity(raw: string | undefined): GoogleIdentity | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(
      Buffer.from(raw, "base64").toString("utf8"),
    );
    return isGoogleIdentity(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function setGoogleIdentityCookie(
  cookieWriter: CookieWriter,
  identity: GoogleIdentity,
): void {
  cookieWriter.set(COOKIE_NAME, encodeGoogleIdentity(identity), {
    // httpOnly: only the /login Server Component reads this, never client JS.
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: ONE_YEAR_SECONDS,
  });
}

export { COOKIE_NAME as GOOGLE_IDENTITY_COOKIE };
