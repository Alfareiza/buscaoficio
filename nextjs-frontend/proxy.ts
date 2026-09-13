import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import {
  clearAuthCookies,
  decodeJwtExpiryMs,
  forwardAuthCookies,
  setAccessTokenCookie,
} from "@/lib/auth-cookies";

const REFRESH_BUFFER_MS = 2 * 60 * 1000;

async function refreshAccessToken(request: NextRequest) {
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

function denyDashboardAccess(request: NextRequest, clearCookies: boolean) {
  // Never 307 a Server Action: Next POSTs it to the current page; a 307 is
  // replayed as Flight, not a navigation (prod Logout no-op).
  if (request.headers.has("next-action")) {
    return NextResponse.next();
  }
  const response = NextResponse.redirect(new URL("/login", request.url));
  if (clearCookies) {
    clearAuthCookies(response.cookies);
  }
  return response;
}

function applyRefreshedCookies(
  response: NextResponse,
  refreshed: { accessToken: string; setCookieHeaders: string[] },
) {
  setAccessTokenCookie(response.cookies, refreshed.accessToken);
  forwardAuthCookies(refreshed.setCookieHeaders, response.cookies);
  return response;
}

export async function proxy(request: NextRequest) {
  const isBackendProxy = request.nextUrl.pathname.startsWith("/api/backend");
  const accessToken = request.cookies.get("accessToken")?.value;

  if (!accessToken) {
    return isBackendProxy
      ? NextResponse.next()
      : denyDashboardAccess(request, false);
  }

  const expiryMs = decodeJwtExpiryMs(accessToken);
  const needsRefresh =
    expiryMs === null || expiryMs - Date.now() < REFRESH_BUFFER_MS;

  if (!needsRefresh) {
    return NextResponse.next();
  }

  const refreshed = await refreshAccessToken(request);
  if (!refreshed) {
    if (isBackendProxy) {
      const response = NextResponse.next();
      clearAuthCookies(response.cookies);
      return response;
    }
    return denyDashboardAccess(request, true);
  }

  return applyRefreshedCookies(NextResponse.next(), refreshed);
}

export const config = {
  matcher: ["/dashboard/:path*", "/api/backend/:path*"],
};
