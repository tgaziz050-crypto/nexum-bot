FROM node:20-slim

WORKDIR /app

# Install edge-tts
RUN apt-get update && apt-get install -y python3 python3-pip curl && \
    pip3 install edge-tts --break-system-packages && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm install

COPY . .

RUN mkdir -p data

EXPOSE 3000

CMD ["npm", "start"]
