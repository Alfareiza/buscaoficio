import { NextRequest, NextResponse } from "next/server";
import { authJwtLogout } from "@/app/clientService";
import { clearAuthCookies } from "@/lib/auth-cookies";

export async function POST(request: NextRequest) {
  const token = request.cookies.get("accessToken")?.value;

  if (token) {
    try {
      await authJwtLogout({ headers: { Authorization: `Bearer ${token}` } });
    } catch {
      // best-effort — always clear and redirect regardless
    }
  }

  const base = process.env.FRONTEND_URL ?? request.nextUrl.origin;
  const response = NextResponse.redirect(`${base}/login`, { status: 303 });
  clearAuthCookies(response.cookies);
  return response;
}
