FROM python:3.13-slim

# instalar ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "music_bot.py"]
