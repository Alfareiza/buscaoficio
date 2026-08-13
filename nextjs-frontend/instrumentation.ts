import * as Sentry from "@sentry/nextjs";

// Next.js instrumentation hook: picks the matching Sentry init per runtime.
// Dynamic imports keep the Node and Edge bundles isolated.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
