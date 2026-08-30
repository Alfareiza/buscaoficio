"use client";

import * as Sentry from "@sentry/nextjs";
import NextError from "next/error";
import { useEffect } from "react";

/**
 * Next.js Flight client message when a Server Action id from a previous
 * frontend build is posted to a newer deploy (`404` +
 * `x-nextjs-action-not-found`). Not an app bug — reload to pick up the
 * current JS. Do not send to Sentry.
 */
const STALE_SERVER_ACTION_MESSAGE =
  "An unexpected response was received from the server.";

export default function GlobalError({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    if (error.message === STALE_SERVER_ACTION_MESSAGE) {
      window.location.reload();
      return;
    }
    Sentry.captureException(error);
  }, [error]);

  return (
    <html>
      <body>
        <NextError statusCode={0} />
      </body>
    </html>
  );
}
