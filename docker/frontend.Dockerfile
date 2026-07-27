# ============================================
# FrigoCore - Frontend Dockerfile
# Vue 3 + TypeScript + Vite
# ============================================

FROM node:20-alpine

# Set environment variables
ENV NODE_ENV=development

# Install dependencies
RUN apk add --no-cache git

# Create app directory
WORKDIR /app

# Install Node.js dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy application code
COPY . .

# Expose port
EXPOSE 5173

# Default command (overridden in docker-compose)
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]