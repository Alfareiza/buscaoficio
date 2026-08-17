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

export async function proxy(request: NextRequest) {
  let accessToken = request.cookies.get("accessToken")?.value;

  if (!accessToken) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const expiryMs = decodeJwtExpiryMs(accessToken);
  const needsRefresh =
    expiryMs === null || expiryMs - Date.now() < REFRESH_BUFFER_MS;

  let refreshedSetCookieHeaders: string[] | null = null;

  if (needsRefresh) {
    const refreshed = await refreshAccessToken(request);
    if (!refreshed) {
      return redirectToLoginClearingCookies(request);
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
    return redirectToLoginClearingCookies(request);
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
