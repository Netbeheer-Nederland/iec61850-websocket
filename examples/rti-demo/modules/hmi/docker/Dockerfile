# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
#
# SPDX-License-Identifier: Apache-2.0

# Build stage
FROM node:26.9.0-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Build-time BFF address (optional): baked into the bundle by Vite. The
# container's BFF_HOST / BFF_PORT (runtime, below) take precedence over these.
ARG VITE_BFF_HOST=
ARG VITE_BFF_PORT=

# Build the application
RUN VITE_BFF_HOST="$VITE_BFF_HOST" VITE_BFF_PORT="$VITE_BFF_PORT" npm run build

# Production stage
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Writes /config.js from BFF_HOST / BFF_PORT at container start (the nginx
# image runs /docker-entrypoint.d/*.sh before starting nginx).
COPY --chmod=755 docker/40-rti-config.sh /docker-entrypoint.d/40-rti-config.sh

# Expose port
EXPOSE 80

# wget is provided by nginx:alpine's busybox base - no extra install needed.
# 127.0.0.1, not localhost: "localhost" resolves to ::1 first here, but
# nginx's `listen 80;` only binds IPv4 - busybox wget doesn't fall back
# to the A record on an IPv6 connection refusal, so every check failed.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
