"use server";

import { cookies } from "next/headers";
import { authJwtLogout } from "@/app/clientService";
import { redirect } from "next/navigation";
import { clearAuthCookies } from "@/lib/auth-cookies";

export async function logout() {
  const cookieStore = await cookies();
  const token = cookieStore.get("accessToken")?.value;

  if (!token) {
    clearAuthCookies(cookieStore);
    return redirect(`/login`);
  }

  const { error } = await authJwtLogout({
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (error) {
    return { message: error };
  }

  clearAuthCookies(cookieStore);
  redirect(`/login`);
}
