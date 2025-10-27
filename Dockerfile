FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: ffmpeg for merging/remuxing by yt-dlp
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install -r requirements.txt

# App source
COPY . .

# Create temp folder for transient downloads
RUN mkdir -p /app/temp

# Default port (Render provides $PORT)
ENV PORT=5231
EXPOSE 5231

# Launch the Flask app; it binds to 0.0.0.0:$PORT inside app.py
CMD ["python", "app.py"]

