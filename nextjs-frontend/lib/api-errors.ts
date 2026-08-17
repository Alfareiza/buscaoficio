/**
 * Detects a 401 from a generated-client call result. On failure the client
 * returns the raw Axios error object rather than a typed shape, so the
 * status can show up as either `.status` or `.response.status` depending on
 * how the call failed — checked defensively rather than trusting one shape.
 */
export function isUnauthorizedError(result: unknown): boolean {
  if (!result || typeof result !== "object") {
    return false;
  }

  const maybeError = result as {
    status?: number;
    response?: { status?: number };
  };

  return maybeError.status === 401 || maybeError.response?.status === 401;
}
