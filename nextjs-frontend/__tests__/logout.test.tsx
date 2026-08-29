import { logout } from "@/components/actions/logout-action";
import { authJwtLogout } from "@/app/clientService";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

jest.mock("../app/clientService", () => ({
  authJwtLogout: jest.fn(),
}));

jest.mock("next/headers", () => {
  const mockGet = jest.fn();
  const mockDelete = jest.fn();
  return {
    cookies: jest.fn().mockResolvedValue({ get: mockGet, delete: mockDelete }),
  };
});

jest.mock("next/navigation", () => ({
  redirect: jest.fn(),
}));

describe("logout action", () => {
  it("clears all three auth cookies and redirects on success", async () => {
    const cookieStore = await cookies();
    (cookieStore.get as jest.Mock).mockReturnValue({ value: "some-token" });
    (authJwtLogout as jest.Mock).mockResolvedValue({ error: undefined });

    await logout();

    expect(authJwtLogout).toHaveBeenCalledWith({
      headers: { Authorization: "Bearer some-token" },
    });
    expect(cookieStore.delete).toHaveBeenCalledWith("accessToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("refreshToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("fingerprintToken");
    expect(redirect).toHaveBeenCalledWith("/login");
  });

  it("clears cookies and redirects even when there is no access token", async () => {
    const cookieStore = await cookies();
    (cookieStore.get as jest.Mock).mockReturnValue(undefined);

    await logout();

    expect(authJwtLogout).not.toHaveBeenCalled();
    expect(cookieStore.delete).toHaveBeenCalledWith("accessToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("refreshToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("fingerprintToken");
    expect(redirect).toHaveBeenCalledWith("/login");
  });

  it("clears cookies and redirects even when the backend logout call fails", async () => {
    const cookieStore = await cookies();
    (cookieStore.get as jest.Mock).mockReturnValue({ value: "stale-token" });
    (authJwtLogout as jest.Mock).mockResolvedValue({
      error: { detail: "unauthorized" },
    });

    await logout();

    expect(cookieStore.delete).toHaveBeenCalledWith("accessToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("refreshToken");
    expect(cookieStore.delete).toHaveBeenCalledWith("fingerprintToken");
    expect(redirect).toHaveBeenCalledWith("/login");
  });
});
