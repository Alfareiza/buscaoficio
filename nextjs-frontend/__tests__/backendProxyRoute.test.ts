/**
 * @jest-environment node
 */
import { NextRequest } from "next/server";

import { GET, POST, DELETE } from "@/app/api/backend/[...path]/route";

function makeRequest(
  path: string,
  init?: ConstructorParameters<typeof NextRequest>[1],
) {
  return new NextRequest(`https://frontend.test/api/backend${path}`, init);
}

function routeContext(path: string) {
  return { params: Promise.resolve({ path: path.split("/").filter(Boolean) }) };
}

describe("GET/POST/DELETE /api/backend/[...path]", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.clearAllMocks();
    process.env.API_BASE_URL = "https://backend.test";
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("forwards a public GET without Authorization", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      new Response(JSON.stringify([{ id: "1", nombre: "Pintura" }]), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const response = await GET(
      makeRequest("/api/v1/catalogo/categorias"),
      routeContext("/api/v1/catalogo/categorias"),
    );

    expect((global.fetch as jest.Mock).mock.calls[0][0].toString()).toBe(
      "https://backend.test/api/v1/catalogo/categorias",
    );
    const [, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(init.headers.get("Authorization")).toBeNull();
    expect(response.status).toBe(200);
  });

  it("attaches Bearer from the accessToken cookie", async () => {
    global.fetch = jest.fn().mockResolvedValue(new Response(null, { status: 204 }));

    await DELETE(
      makeRequest("/api/v1/items/abc", {
        method: "DELETE",
        headers: { cookie: "accessToken=cookie-token" },
      }),
      routeContext("/api/v1/items/abc"),
    );

    const [, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(init.headers.get("Authorization")).toBe("Bearer cookie-token");
  });

  it("blocks auth routes so OTP/refresh cannot be proxied", async () => {
    global.fetch = jest.fn();

    const response = await POST(
      makeRequest("/api/v1/otp/verify", { method: "POST" }),
      routeContext("/api/v1/otp/verify"),
    );

    expect(response.status).toBe(404);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("does not forward upstream Set-Cookie", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: {
          "content-type": "application/json",
          "set-cookie": "refreshToken=leaked; HttpOnly",
        },
      }),
    );

    const response = await GET(
      makeRequest("/api/v1/catalogo/zonas"),
      routeContext("/api/v1/catalogo/zonas"),
    );

    expect(response.headers.get("set-cookie")).toBeNull();
  });
});
