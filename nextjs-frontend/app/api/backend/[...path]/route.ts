import { NextResponse, type NextRequest } from "next/server";

type RouteContext = { params: Promise<{ path: string[] }> };

function isAuthPath(path: string) {
  return (
    path.startsWith("/api/v1/otp") ||
    path.startsWith("/api/v1/register") ||
    path.startsWith("/api/v1/auth/google") ||
    path.startsWith("/api/v1/auth/jwt/refresh") ||
    path.startsWith("/api/v1/auth/jwt/logout")
  );
}

async function proxyToBackend(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const backendPath = `/${path.join("/")}`;

  if (isAuthPath(backendPath)) {
    return NextResponse.json({ detail: "Use the dedicated auth route." }, { status: 404 });
  }

  const apiBaseUrl = process.env.API_BASE_URL;
  if (!apiBaseUrl) {
    return NextResponse.json({ detail: "API_BASE_URL is not configured." }, { status: 500 });
  }

  const target = new URL(backendPath, apiBaseUrl.endsWith("/") ? apiBaseUrl : `${apiBaseUrl}/`);
  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.append(key, value);
  });

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  const accessToken = request.cookies.get("accessToken")?.value;
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const method = request.method;
  const upstream = await fetch(target, {
    method,
    headers,
    body: method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer(),
    redirect: "manual",
    cache: "no-store",
  });

  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("set-cookie");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxyToBackend;
export const POST = proxyToBackend;
export const PUT = proxyToBackend;
export const PATCH = proxyToBackend;
export const DELETE = proxyToBackend;
