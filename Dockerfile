# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# BASE_PATH sets the subpath prefix (e.g. "/bitaxe" for reverse proxy).
# Defaults to "/" for root-level deployments.
ARG BASE_PATH=/
ENV BASE_PATH=${BASE_PATH}

# Build the frontend
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python source
COPY src/ ./src/
COPY bitaxe_hashrate_benchmark.py .

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/src/web/static ./src/web/static

# Create data directories and copy default config
RUN mkdir -p /results /config
COPY config.json /config/config.json
VOLUME /results
VOLUME /config

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV RESULTS_DIR=/results
ENV CONFIG_DIR=/config

# Expose the web server port
EXPOSE 8000

# Default to running the web UI
# Override with "benchmark" to run CLI mode
ENTRYPOINT ["python", "bitaxe_hashrate_benchmark.py"]

# Default command is to serve the web UI
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
