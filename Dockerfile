FROM node:20-slim

WORKDIR /app

RUN apt-get update && apt-get install -y python3 python3-pip curl && \
    pip3 install edge-tts --break-system-packages && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm install

COPY . .

# Compile TypeScript
RUN npx tsc --skipLibCheck || true

# Copy public files into dist (Mini Apps fix)
RUN cp -r src/public dist/public 2>/dev/null || true

RUN mkdir -p data

EXPOSE 3000

CMD ["node", "dist/index.js"]
