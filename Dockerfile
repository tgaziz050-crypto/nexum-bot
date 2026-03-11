FROM node:20-slim

# Install system deps for voice processing
RUN apt-get update && apt-get install -y \
    ffmpeg python3 python3-pip \
    && pip3 install edge-tts --break-system-packages \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

EXPOSE 3000 18790

CMD ["node", "dist/index.js"]
