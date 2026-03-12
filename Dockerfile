FROM node:20-slim

# 1. System deps + Python + ffmpeg (нужен для конвертации аудио)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    ffmpeg curl ca-certificates sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 2. Edge-TTS в отдельном venv — самый надёжный способ
RUN python3 -m venv /opt/edge-tts-env \
    && /opt/edge-tts-env/bin/pip install --no-cache-dir edge-tts \
    && /opt/edge-tts-env/bin/edge-tts --version

# 3. Симлинк чтобы вызывать просто edge-tts из любого места
RUN ln -s /opt/edge-tts-env/bin/edge-tts /usr/local/bin/edge-tts \
    && ln -s /opt/edge-tts-env/bin/python3 /usr/local/bin/edge-python3

# 4. Проверяем что edge-tts доступен
RUN edge-tts --version && echo "✅ edge-tts OK"

WORKDIR /app

# 5. Node deps
COPY package.json ./
RUN npm install --legacy-peer-deps

# 6. App source
COPY tsconfig.json ./
COPY src ./src
COPY nexum_agent.py ./

# 7. Data dir для SQLite volume
RUN mkdir -p /data && chmod 777 /data

ENV NODE_ENV=production
ENV PORT=3000
ENV EDGE_TTS_PATH=/usr/local/bin/edge-tts
ENV EDGE_PYTHON_PATH=/usr/local/bin/edge-python3

EXPOSE 3000

CMD ["./node_modules/.bin/ts-node", "--project", "tsconfig.json", "src/index.ts"]
