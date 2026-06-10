# Build stage
FROM node:20-slim AS builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Production stage — non-root nginx on port 8080
FROM nginx:1.27-bookworm AS runner

RUN adduser --system --no-create-home --disabled-login appuser \
    && chown -R appuser /var/cache/nginx \
    && chown -R appuser /var/log/nginx \
    && touch /tmp/nginx.pid \
    && chown appuser /tmp/nginx.pid

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
RUN chown -R appuser /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

USER appuser
EXPOSE 8080
CMD ["nginx", "-g", "daemon off; pid /tmp/nginx.pid;"]
