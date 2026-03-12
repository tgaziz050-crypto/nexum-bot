FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl ca-certificates sqlite3 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install edge-tts (Microsoft Neural TTS — free, 400+ voices, all languages)
RUN pip3 install edge-tts --break-system-packages

WORKDIR /app

COPY package.json ./
RUN npm install --legacy-peer-deps

COPY tsconfig.json ./
COPY src ./src

RUN npm run build || true

COPY nexum_agent.py ./

ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000

CMD ["node", "dist/index.js"]
