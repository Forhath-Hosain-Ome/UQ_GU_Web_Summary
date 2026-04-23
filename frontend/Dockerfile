FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci --frozen-lockfile

COPY . .

# Build static assets for production
RUN npm run build

# ── Runtime stage (Nginx serves built assets) ──────────────────
FROM nginx:1.27-alpine
WORKDIR /usr/share/nginx/html

# Remove default nginx content
RUN rm -rf ./*

COPY --from=builder /app/dist .
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

# CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
