# syntax=docker/dockerfile:1

# ──────────────────────────────────────────────
# Stage 1: Install dependencies
# ──────────────────────────────────────────────
FROM node:22-alpine AS deps
WORKDIR /app

# Copy only package manifests for layer caching
COPY package.json package-lock.json ./
RUN npm ci

# ──────────────────────────────────────────────
# Stage 2: Build the application
# ──────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app

# Copy installed dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next.js build-time env vars (must be available at build time)
# NEXT_PUBLIC_* vars are inlined into the client bundle at build time.
# Set these via --build-arg or .env file if needed.
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_SUPABASE_URL=""
ENV NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=""

RUN npm run build

# ──────────────────────────────────────────────
# Stage 3: Production runner
# ──────────────────────────────────────────────
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Install bash for interactive debugging
RUN apk add --no-cache bash

# Copy standalone output (Next.js standalone mode)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]
