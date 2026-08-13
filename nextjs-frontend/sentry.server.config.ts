import * as Sentry from "@sentry/nextjs";

// Node.js runtime only (Server Components, Server Actions, Route Handlers).
// Loaded from instrumentation.ts when NEXT_RUNTIME === "nodejs".
Sentry.init({
  dsn: process.env.SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
  enableLogs: true,
});
