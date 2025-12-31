FROM python:3.12-slim

# =========================
# System deps
# =========================
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# =========================
# Workdir
# =========================
WORKDIR /app

# =========================
# Python deps
# =========================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =========================
# App files
# =========================
COPY . .

# =========================
# Run bot
# =========================
CMD ["python", "music_bot.py"]
