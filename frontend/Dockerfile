# Multi-stage frontend: Vite for local development, Nginx for production.
FROM node:24-alpine AS dev
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

FROM dev AS build
RUN npm run build


# Stage 2: Production Nginx Server
FROM nginx:alpine AS prod

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy production assets and the API/SPA reverse-proxy configuration.
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose HTTP port
EXPOSE 80

# Run nginx
CMD ["nginx", "-g", "daemon off;"]
