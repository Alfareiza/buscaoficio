import * as Sentry from "@sentry/nextjs";

// Browser bundle. Next.js loads this file automatically; it cannot share
// Sentry.init() with server/edge (those are different JS runtimes).
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
  enableLogs: true,
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
