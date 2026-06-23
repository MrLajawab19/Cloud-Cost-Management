# ── Stage 1: Build the React app ─────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Build arg for API URL (set via docker-compose)
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json .
RUN npm install

COPY . .
RUN npm run build

# ── Stage 2: Serve with nginx ─────────────────────────────────────
FROM nginx:alpine

# Copy built React files
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config: redirect all routes to index.html (SPA support)
RUN echo 'server { \
  listen 80; \
  location / { \
    root /usr/share/nginx/html; \
    index index.html; \
    try_files $uri $uri/ /index.html; \
  } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
