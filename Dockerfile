# ClawBench HF Docker Space
# Two-stage: build OpenClaw from source, then Python harness

# --- Stage 1: Build OpenClaw from source ---
FROM node:22-bookworm-slim AS gateway-build

RUN apt-get update && apt-get install -y git python3 make g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# Clone latest main and install + build with all extensions
RUN git clone --depth 1 https://github.com/openclaw/openclaw.git . && \
    npm install && \
    npm run build

# --- Stage 2: Runtime ---
FROM python:3.11-slim-bookworm

# Install Node.js 22
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Copy built OpenClaw from stage 1 (includes all extensions + node_modules)
COPY --from=gateway-build /build /openclaw

# HF Space user (UID 1000 required)
RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

# Copy everything needed for pip install
COPY --chown=user pyproject.toml README.md ./
COPY --chown=user clawbench/ clawbench/
COPY --chown=user tasks/ tasks/
COPY --chown=user app.py .

RUN pip install --no-cache-dir .

# Create dirs for gateway state and benchmark data
RUN mkdir -p /data/results /data/queue /home/user/.openclaw && \
    chmod -R 777 /data /home/user/.openclaw

USER user

# Gateway config: headless, token auth, allow-unconfigured
ENV GATEWAY_PORT=18789
ENV OPENCLAW_GATEWAY_TOKEN=clawbench-internal-token
ENV OPENCLAW_HOME=/home/user
ENV OPENCLAW_STATE_DIR=/home/user/.openclaw

EXPOSE 7860
CMD ["python", "app.py"]
