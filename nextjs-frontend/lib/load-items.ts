import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { readItem } from "@/app/clientService";
import { isUnauthorizedError } from "@/lib/api-errors";
import { clearAuthCookies } from "@/lib/auth-cookies";

/** RSC data load — not a Server Action. Calls FastAPI directly with the
 * HttpOnly cookie. Mutations that need `useActionState` stay in
 * `items-action.ts`; client deletes go through `/api/backend`. */
export async function loadItems(page: number = 1, size: number = 10) {
  const cookieStore = await cookies();
  const token = cookieStore.get("accessToken")?.value;

  if (!token) {
    return { message: "No access token found" };
  }

  const result = await readItem({
    query: {
      page: page,
      size: size,
    },
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  const { data, error } = result;

  if (error) {
    if (isUnauthorizedError(result)) {
      clearAuthCookies(cookieStore);
      return redirect("/login");
    }
    return { message: error };
  }

  return data;
}
