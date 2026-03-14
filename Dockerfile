FROM node:20-slim

WORKDIR /app

RUN apt-get update && apt-get install -y python3 python3-pip curl && \
    pip3 install edge-tts --break-system-packages && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

RUN mkdir -p data

EXPOSE 3000

CMD ["node", "dist/index.js"]
