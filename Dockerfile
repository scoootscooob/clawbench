# ClawBench HF Docker Space
FROM python:3.11-slim-bookworm

# Install Node.js 22
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install OpenClaw gateway from npm + missing extension deps
RUN npm install -g openclaw@latest && \
    cd /usr/lib/node_modules/openclaw && \
    npm install @buape/carbon@0.14.0 2>/dev/null || true

# HF Space user (UID 1000 required)
RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:/usr/lib/node_modules/.bin:$PATH

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
