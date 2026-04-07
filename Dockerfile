# ClawBench HF Docker Space
# Single-stage: Node.js (gateway via npm) + Python (harness + Gradio)

FROM python:3.11-slim-bookworm

# Install Node.js 22
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install OpenClaw gateway from npm (no source build needed)
RUN npm install -g openclaw@latest

# HF Space user (UID 1000 required)
RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:/usr/lib/node_modules/.bin:$PATH

WORKDIR /home/user/app

# Install Python package
COPY --chown=user pyproject.toml .
COPY --chown=user clawbench/ clawbench/
COPY --chown=user tasks/ tasks/
COPY --chown=user app.py .
RUN pip install --no-cache-dir -e .

# Persistent storage
RUN mkdir -p /data/results /data/queue && chmod -R 777 /data

USER user

EXPOSE 7860

ENV GATEWAY_PORT=18789
ENV OPENCLAW_GATEWAY_TOKEN=""

CMD ["python", "app.py"]
