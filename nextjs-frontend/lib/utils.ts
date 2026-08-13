import { AuthJwtLoginError, RegisterRegisterError } from "@/app/clientService";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getErrorMessage(
  error: RegisterRegisterError | AuthJwtLoginError,
): string {
  let errorMessage = "An unknown error occurred";

  if (typeof error.detail === "string") {
    // If detail is a string, use it directly
    errorMessage = error.detail;
  } else if (
    typeof error.detail === "object" &&
    error.detail !== null &&
    "reason" in error.detail &&
    typeof error.detail.reason === "string"
  ) {
    errorMessage = error.detail.reason;
  }

  return errorMessage;
}
