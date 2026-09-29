# Multi-stage Frontend Dockerfile

# Stage 1: Development and Build
FROM node:20-alpine AS dev
WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Default dev command
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Build production static files
RUN npm run build


# Stage 2: Production Nginx Server
FROM nginx:alpine AS prod

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from dev/build stage
COPY --from=dev /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Run nginx
CMD ["nginx", "-g", "daemon off;"]
