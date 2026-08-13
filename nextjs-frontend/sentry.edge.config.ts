import * as Sentry from "@sentry/nextjs";

// Edge runtime only (proxy.ts). Kept as its own file so Node-only APIs
// never get bundled into Edge. Loaded when NEXT_RUNTIME === "edge".
Sentry.init({
  dsn: process.env.SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
  enableLogs: true,
});
