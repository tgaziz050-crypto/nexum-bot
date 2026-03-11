FROM node:22-alpine

# Python + edge-tts для TTS
RUN apk add --no-cache python3 py3-pip \
 && pip3 install edge-tts --break-system-packages

WORKDIR /app

# Устанавливаем все зависимости (включая devDeps для сборки)
COPY package*.json ./
RUN npm install

# Копируем исходники и компилируем TypeScript
COPY . .
RUN npm run build

# Убираем devDependencies
RUN npm prune --omit=dev

ENV NODE_ENV=production

CMD ["node", "dist/index.js"]
