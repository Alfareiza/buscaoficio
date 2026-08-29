"use server";

import { cookies } from "next/headers";
import { authJwtLogout } from "@/app/clientService";
import { redirect } from "next/navigation";
import { clearAuthCookies } from "@/lib/auth-cookies";

export async function logout() {
  const cookieStore = await cookies();
  const token = cookieStore.get("accessToken")?.value;

  // Best-effort revoke. A dead or rejected token must still end the
  // local session — the Logout button ignores a returned `{ message }`.
  if (token) {
    await authJwtLogout({
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
  }

  clearAuthCookies(cookieStore);
  redirect(`/login`);
}
