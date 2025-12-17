# K3s MCP Server Dockerfile
FROM node:20-alpine

LABEL org.opencontainers.image.title="K3s MCP Server"
LABEL org.opencontainers.image.description="MCP server for K3s/Kubernetes cluster management"
LABEL org.opencontainers.image.source="https://github.com/ry-ops/k3s-mcp-server"
LABEL org.opencontainers.image.vendor="ry-ops"

# Install kubectl and runtime dependencies
RUN apk add --no-cache \
    ca-certificates \
    curl \
    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production && npm cache clean --force

# Copy MCP server files
COPY . .

# Create non-root user
RUN addgroup -g 1001 -S k3s && \
    adduser -S -u 1001 -G k3s k3s && \
    chown -R k3s:k3s /app

USER k3s

ENV NODE_ENV=production
ENV MCP_SERVER_TYPE=k3s

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))" || exit 1

CMD ["node", "index.js"]
