import * as Sentry from "@sentry/nextjs";
import { NextResponse, type NextRequest } from "next/server";

import { authGoogleSession } from "@/app/clientService";
import { forwardAuthCookies, setAccessTokenCookie } from "@/lib/auth-cookies";
import { setGoogleIdentityCookie } from "@/lib/google-identity-cookie";

/** Where GET /api/v1/auth/google/callback sends the browser after Google
 * verifies an existing user.
 *
 * This is a Route Handler, not a page, on purpose: it runs entirely on the
 * server before anything renders, so the browser goes Google → backend →
 * here → /dashboard with no intermediate screen, spinner, or flash. A page
 * would have to mount, run an effect to exchange the token, and only then
 * navigate — which is exactly the visible in-between state this avoids.
 *
 * The token exchange has to happen on the Next.js server (rather than
 * FastAPI's callback just setting cookies itself) because session cookies
 * must be set on this origin — see docs/auth.md's cookie-forwarding
 * section.
 */
/** Route Handlers on the Node.js runtime (unlike middleware, which Next
 * normalizes same-origin redirects for) ship request.url's origin verbatim
 * in the Location header. Behind Caddy's reverse proxy, that origin
 * resolves to the standalone server's own bind address (0.0.0.0:3000), not
 * the public domain — confirmed by curling the frontend container directly
 * with an explicit correct Host header and still getting 0.0.0.0:3000 back.
 * FRONTEND_URL is the same explicit-config workaround auth.py already uses
 * for this exact reason; falling back to request.url keeps local dev (no
 * reverse proxy, no FRONTEND_URL set) working unchanged. */
function absoluteUrl(pathAndQuery: string, request: NextRequest): URL {
  return new URL(pathAndQuery, process.env.FRONTEND_URL ?? request.url);
}

export async function GET(request: NextRequest) {
  const loginUrl = absoluteUrl("/login?error=google_auth_failed", request);
  const token = request.nextUrl.searchParams.get("google_session_token");

  if (!token) {
    Sentry.logger.warn(
      "Google Sign-In complete route hit with no google_session_token",
    );
    return NextResponse.redirect(loginUrl);
  }

  try {
    const result = await authGoogleSession({
      body: { google_session_token: token },
    });
    const { data, error } = result;

    if (
      error ||
      !data ||
      typeof data !== "object" ||
      typeof (data as { access_token?: unknown }).access_token !== "string"
    ) {
      Sentry.logger.warn("Google Sign-In session exchange rejected by backend", {
        error,
      });
      return NextResponse.redirect(loginUrl);
    }

    const response = NextResponse.redirect(absoluteUrl("/dashboard", request));

    setAccessTokenCookie(
      response.cookies,
      (data as { access_token: string }).access_token,
    );
    forwardAuthCookies(
      result.headers?.["set-cookie"] as string[] | undefined,
      response.cookies,
    );

    const { nombre_completo, email, picture } = data as {
      nombre_completo?: unknown;
      email?: unknown;
      picture?: unknown;
    };
    if (typeof nombre_completo === "string" && typeof email === "string") {
      setGoogleIdentityCookie(response.cookies, {
        name: nombre_completo,
        email,
        picture: typeof picture === "string" ? picture : null,
      });
    }

    Sentry.logger.info("Google Sign-In: user logged in");
    return response;
  } catch (error) {
    Sentry.captureException(error);
    return NextResponse.redirect(loginUrl);
  }
}
