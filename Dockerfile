# ClawBench HF Docker Space
# Two-stage: build OpenClaw gateway from source, then Python harness

# --- Stage 1: Build OpenClaw from source (skip canvas UI assets) ---
FROM node:22-bookworm-slim AS gateway-build

RUN apt-get update && apt-get install -y git python3 make g++ && rm -rf /var/lib/apt/lists/*
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /build
RUN git clone --depth 1 https://github.com/openclaw/openclaw.git .
RUN pnpm install

# Create a stub canvas bundle so tsdown doesn't fail on missing import
RUN mkdir -p src/canvas-host/a2ui && \
    echo "export default '';" > src/canvas-host/a2ui/a2ui.bundle.js && \
    echo "stub" > src/canvas-host/a2ui/.bundle.hash

# Run individual build steps (skip canvas:a2ui:bundle which needs vendor/ assets)
RUN pnpm exec tsdown --logLevel warn && \
    node scripts/runtime-postbuild.mjs && \
    node scripts/build-stamp.mjs

# --- Stage 2: Runtime ---
FROM python:3.11-slim-bookworm

RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

COPY --from=gateway-build /build/dist /openclaw/dist
COPY --from=gateway-build /build/node_modules /openclaw/node_modules
COPY --from=gateway-build /build/package.json /openclaw/package.json
COPY --from=gateway-build /build/extensions /openclaw/extensions

RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

COPY --chown=user pyproject.toml README.md ./
COPY --chown=user clawbench/ clawbench/
COPY --chown=user tasks/ tasks/
COPY --chown=user app.py .

RUN pip install --no-cache-dir .

RUN mkdir -p /data/results /data/queue /home/user/.openclaw && \
    chmod -R 777 /data /home/user/.openclaw

USER user

ENV GATEWAY_PORT=18789
ENV OPENCLAW_GATEWAY_TOKEN=clawbench-internal-token
ENV OPENCLAW_HOME=/home/user
ENV OPENCLAW_STATE_DIR=/home/user/.openclaw

EXPOSE 7860
CMD ["python", "app.py"]
