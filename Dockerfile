FROM python:3.12-slim

# =========================
# INSTALAR FFMPEG COMPLETO
# =========================
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# =========================
# DIRETÓRIO
# =========================
WORKDIR /app

# =========================
# DEPENDÊNCIAS
# =========================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =========================
# CÓDIGO
# =========================
COPY . .

# =========================
# START
# =========================
CMD ["python", "music_bot.py"]
