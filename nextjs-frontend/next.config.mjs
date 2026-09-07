import { withSentryConfig } from "@sentry/nextjs";
import ForkTsCheckerWebpackPlugin from "fork-ts-checker-webpack-plugin";
import process from "node:process";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Note: `output: "standalone"` (Docker self-hosting) was removed when the
  // frontend moved to Vercel — Vercel bundles differently and doesn't use the
  // standalone server. Restore it in the `ec2` branch for Docker/EC2 deploys.
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.plugins.push(
        new ForkTsCheckerWebpackPlugin({
          async: true, // Run type checking synchronously to block the build
          typescript: {
            configOverwrite: {
              compilerOptions: {
                skipLibCheck: true,
              },
            },
          },
        }),
      );
    }
    return config;
  },
};

export default withSentryConfig(nextConfig, {
  org: "aag-k0",
  project: "buscaoficio-frontend",
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
});
