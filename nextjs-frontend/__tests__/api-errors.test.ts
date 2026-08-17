import { isUnauthorizedError } from "@/lib/api-errors";

describe("isUnauthorizedError", () => {
  it("detects a top-level status of 401", () => {
    expect(isUnauthorizedError({ status: 401 })).toBe(true);
  });

  it("detects a nested response.status of 401 (Axios error shape)", () => {
    expect(isUnauthorizedError({ response: { status: 401 } })).toBe(true);
  });

  it("returns false for other status codes", () => {
    expect(isUnauthorizedError({ status: 404 })).toBe(false);
    expect(isUnauthorizedError({ response: { status: 500 } })).toBe(false);
  });

  it("returns false for non-object input", () => {
    expect(isUnauthorizedError(null)).toBe(false);
    expect(isUnauthorizedError(undefined)).toBe(false);
    expect(isUnauthorizedError("error")).toBe(false);
  });
});
