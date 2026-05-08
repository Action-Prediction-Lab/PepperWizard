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

COPY stt-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the Whisper model into the image so first-boot is fast and offline-capable.
# Reads model_size from pepper_wizard/config/stt.json 
# shared with the runtime config (mounted at /app/pepper_config/stt.json).
# HF_HOME points outside /app so the runtime bind-mount of ./stt-service:/app
ENV HF_HOME=/opt/whisper-cache
COPY pepper_wizard/config/stt.json /tmp/stt.json
RUN mkdir -p ${HF_HOME} && \
    python -c "import json; from faster_whisper import WhisperModel; \
m = json.load(open('/tmp/stt.json')).get('model_size', 'base.en'); \
print(f'[build] baking whisper model: {m}'); \
WhisperModel(m, device='cpu', compute_type='int8')"

COPY stt-service/. .

CMD ["python", "main.py"]
