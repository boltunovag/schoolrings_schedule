FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    mpg123 \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

COPY audio_files/ /app/audio_files/
WORKDIR /app

CMD ["mpg123", "-v", "/app/audio_files/end_11.mp3"]

