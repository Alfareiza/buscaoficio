import { withSentryConfig } from "@sentry/nextjs";
import ForkTsCheckerWebpackPlugin from "fork-ts-checker-webpack-plugin";
import process from "node:process";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Traces only the files node server.js needs. Dockerfile.prod copies
  // .next/standalone into a slim alpine runner — without this, the image
  // ships Debian + full node_modules + webpack cache (~GB, too big for the EC2).
  output: "standalone",
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
