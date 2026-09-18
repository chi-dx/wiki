FROM node:24.16.0-bookworm-slim
WORKDIR /app/compiler-service
COPY compiler-service/package*.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY compiler-service/*.mjs ./
COPY fixtures /app/fixtures
ENV COMPILER_HOST=0.0.0.0 COMPILER_ROOT=/compiler-data
CMD ["node", "server.mjs"]
