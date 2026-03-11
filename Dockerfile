FROM python:3.11-slim

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp через pip
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app

# Зависимости (включая shazamio для распознавания музыки)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код
COPY bot.py .
COPY nexum_agent.py .

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["python", "-u", "bot.py"]
