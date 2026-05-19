# RTI Demo Frontend Docker Image
FROM node:18-slim

# Set working directory
WORKDIR /app

# Copy frontend files
COPY . .

# Install dependencies (if package.json exists)
RUN if [ -f package.json ]; then npm install; fi

# Expose port
EXPOSE 8080

# Start static server
CMD ["npx", "http-server", "-p", "8080", "-c-1"]
