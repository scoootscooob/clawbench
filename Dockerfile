# ClawBench HF Docker Space
# Two-stage: build OpenClaw gateway from source, then Python harness

# --- Stage 1: Build OpenClaw from source (skip canvas UI assets) ---
FROM node:22-bookworm-slim AS gateway-build

ARG OPENCLAW_REPO=https://github.com/scoootscooob/openclaw.git
ARG OPENCLAW_REF=5682ec37fada89205821ee16a03f1e0d0948efb7

RUN apt-get update && apt-get install -y git python3 make g++ && rm -rf /var/lib/apt/lists/*
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /build
RUN git init . && \
    git remote add origin ${OPENCLAW_REPO} && \
    git fetch --depth 1 origin ${OPENCLAW_REF} && \
    git checkout FETCH_HEAD
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
FROM node:22-bookworm-slim

RUN apt-get update && \
    apt-get install -y python3 python3-pip python-is-python3 curl lsof git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=gateway-build /build/dist /openclaw/dist
COPY --from=gateway-build /build/node_modules /openclaw/node_modules
COPY --from=gateway-build /build/package.json /openclaw/package.json
COPY --from=gateway-build /build/extensions /openclaw/extensions

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npm install --prefix /openclaw playwright@1.59.1 && \
    npx --prefix /openclaw playwright install --with-deps chromium && \
    CHROME_PATH="$(echo /ms-playwright/chromium-*/chrome-linux/chrome)" && \
    test -x "$CHROME_PATH" && \
    ln -sf "$CHROME_PATH" /usr/bin/chromium

RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

COPY --chown=user pyproject.toml README.md ./
COPY --chown=user clawbench/ clawbench/
COPY --chown=user tasks/ tasks/
COPY --chown=user baselines/ baselines/
COPY --chown=user app.py .

RUN python3 -m pip install --break-system-packages --no-cache-dir '.[dev]'

RUN mkdir -p \
    /data/results \
    /data/queue \
    /home/user/.openclaw/agents/dev \
    /home/user/.openclaw/agents/main/agent && \
    chown -R user:user /data /home/user/.openclaw && \
    chmod -R 777 /data /home/user/.openclaw

USER user

ENV GATEWAY_PORT=18789
ENV OPENCLAW_HOME=/home/user
ENV OPENCLAW_STATE_DIR=/home/user/.openclaw

EXPOSE 7860
CMD ["python", "app.py"]
