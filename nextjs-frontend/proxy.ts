import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { usersCurrentUser } from "@/app/clientService";
import {
  clearAuthCookies,
  decodeJwtExpiryMs,
  forwardAuthCookies,
  setAccessTokenCookie,
} from "@/lib/auth-cookies";

// Refresh proactively before the access token actually expires, so a
// request never has to eat a 401 mid-flight.
const REFRESH_BUFFER_MS = 2 * 60 * 1000;

type RefreshResult = { accessToken: string; setCookieHeaders: string[] };

/**
 * Calls FastAPI's refresh endpoint server-to-server, forwarding the
 * refresh/fingerprint cookies manually as a Cookie header — server-to-server
 * fetches don't auto-attach the browser's cookies the way a same-origin
 * browser request would.
 */
async function refreshAccessToken(
  request: NextRequest,
): Promise<RefreshResult | null> {
  const refreshToken = request.cookies.get("refreshToken")?.value;
  const fingerprintToken = request.cookies.get("fingerprintToken")?.value;

  if (!refreshToken || !fingerprintToken) {
    return null;
  }

  const response = await fetch(
    `${process.env.API_BASE_URL}/api/v1/auth/jwt/refresh`,
    {
      method: "POST",
      headers: {
        Cookie: `refreshToken=${refreshToken}; fingerprintToken=${fingerprintToken}`,
      },
    },
  );

  if (!response.ok) {
    return null;
  }

  const data = (await response.json()) as { access_token?: string };
  if (!data.access_token) {
    return null;
  }

  return {
    accessToken: data.access_token,
    setCookieHeaders: response.headers.getSetCookie(),
  };
}

function redirectToLoginClearingCookies(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/login", request.url));
  clearAuthCookies(response.cookies);
  return response;
}

/**
 * Document GETs with a dead session 307 to /login. Server Action POSTs
 * must not: Next posts the action to the current page (POST /dashboard
 * + `next-action`), and a middleware 307 is followed as another Flight
 * POST (method and body preserved). The client never treats that as a
 * navigation, so Logout appears to do nothing. Let the action run; it
 * issues `redirect()` itself.
 */
function denyDashboardAccess(request: NextRequest, clearCookies: boolean) {
  if (request.headers.has("next-action")) {
    return NextResponse.next();
  }
  if (clearCookies) {
    return redirectToLoginClearingCookies(request);
  }
  return NextResponse.redirect(new URL("/login", request.url));
}

export async function proxy(request: NextRequest) {
  let accessToken = request.cookies.get("accessToken")?.value;

  if (!accessToken) {
    return denyDashboardAccess(request, false);
  }

  const expiryMs = decodeJwtExpiryMs(accessToken);
  const needsRefresh =
    expiryMs === null || expiryMs - Date.now() < REFRESH_BUFFER_MS;

  let refreshedSetCookieHeaders: string[] | null = null;

  if (needsRefresh) {
    const refreshed = await refreshAccessToken(request);
    if (!refreshed) {
      return denyDashboardAccess(request, true);
    }
    accessToken = refreshed.accessToken;
    refreshedSetCookieHeaders = refreshed.setCookieHeaders;
  }

  const options = {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  };

  const { error } = await usersCurrentUser(options);

  if (error) {
    return denyDashboardAccess(request, true);
  }

  const response = NextResponse.next();

  if (refreshedSetCookieHeaders) {
    setAccessTokenCookie(response.cookies, accessToken);
    forwardAuthCookies(refreshedSetCookieHeaders, response.cookies);
  }

  return response;
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
