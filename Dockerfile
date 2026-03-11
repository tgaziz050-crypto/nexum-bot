FROM node:22-alpine

RUN apk add --no-cache python3 py3-pip make g++ \
 && pip3 install edge-tts --break-system-packages

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

RUN npm prune --omit=dev

ENV NODE_ENV=production

CMD ["node", "dist/index.js"]
