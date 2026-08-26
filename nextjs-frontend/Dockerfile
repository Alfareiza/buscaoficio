FROM node:20-bookworm

# Set the working directory
WORKDIR /app

# Corepack (bundled with Node 20) reads packageManager in package.json and
# installs that exact, hash-verified pnpm version — see Dockerfile.prod for
# why an unpinned `npm install -g pnpm` is unsafe here.
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && corepack prepare --activate

# Install dependencies as root (or myappuser, depending on your structure)
RUN pnpm install

## Switch to the non-root user
USER node

# Copy the rest of your application code
COPY . .

EXPOSE 3000

# Start the application
CMD ["./start.sh"]