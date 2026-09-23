FROM oven/bun:latest AS base
WORKDIR /app

# Copy package files and install dependencies
COPY package.json bun.lockb ./
RUN bun install

# Copy the rest of the source code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Default command to start dev server
CMD ["bun", "dev"]
