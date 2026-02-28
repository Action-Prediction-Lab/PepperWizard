FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for sounddevice (PortAudio) and PulseAudio
RUN apt-get update && apt-get install -y \
    libportaudio2 \
    libsndfile1 \
    libpulse0 \
    libasound2-plugins \
    pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

# Configure ALSA to route through PulseAudio (PortAudio uses ALSA backend)
RUN echo '\
    pcm.!default {\n\
    type pulse\n\
    }\n\
    ctl.!default {\n\
    type pulse\n\
    }\n' > /etc/asound.conf

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
