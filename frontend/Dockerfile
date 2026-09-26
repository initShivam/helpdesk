FROM node:20-alpine AS base
WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the source code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Default command to start dev server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
