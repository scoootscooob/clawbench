# ClawBench HF Docker Space
# Runtime image with published OpenClaw package plus Python harness.

FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y python3 python3-pip python-is-python3 curl lsof git && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g openclaw@2026.4.9 && \
    OPENCLAW_NPM_ROOT="$(npm root -g)" && \
    test -f "${OPENCLAW_NPM_ROOT}/openclaw/dist/index.js" && \
    ln -s "${OPENCLAW_NPM_ROOT}/openclaw" /openclaw

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npx -y playwright@1.58.2 install --with-deps chromium && \
    CHROME_PATH="$(echo /ms-playwright/chromium-*/chrome-linux/chrome)" && \
    test -x "$CHROME_PATH" && \
    ln -sf "$CHROME_PATH" /usr/bin/chromium

ENV HOME=/home/node PATH=/home/node/.local/bin:$PATH

WORKDIR /home/node/app

COPY --chown=node:node pyproject.toml README.md ./
COPY --chown=node:node clawbench/ clawbench/
COPY --chown=node:node tasks/ tasks/
COPY --chown=node:node baselines/ baselines/
COPY --chown=node:node app.py .

RUN python3 -m pip install --break-system-packages --no-cache-dir '.[dev]'

RUN mkdir -p \
    /data/results \
    /data/queue \
    /home/node/.openclaw/agents/dev \
    /home/node/.openclaw/agents/main/agent && \
    chown -R node:node /data /home/node/.openclaw && \
    chmod -R 777 /data /home/node/.openclaw

USER node

ENV GATEWAY_PORT=18789
ENV OPENCLAW_HOME=/home/node
ENV OPENCLAW_STATE_DIR=/home/node/.openclaw

EXPOSE 7860
CMD ["python", "app.py"]
