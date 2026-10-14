FROM python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a9fc0e6e38295747e49ac0

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libportaudio2 \
    libsndfile1 \
    libpulse0 \
    libasound2-plugins \
    pulseaudio-utils \
    ffmpeg \
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

# PIP_CONSTRAINT pins every pip install to the versions defined in docker/constraints-stt.txt
COPY docker/constraints-stt.txt .
ENV PIP_CONSTRAINT=/app/constraints-stt.txt

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu124 torch torchaudio \
 && pip install --no-cache-dir -r requirements.txt

 
ENV HF_HOME=/opt/asr-cache
COPY pepper_wizard/config/stt.json /tmp/stt.json
COPY stt-service/bake_models.py stt-service/config_loader.py stt-service/vad_segmenter.py /tmp/
RUN mkdir -p ${HF_HOME} && \
    PYTHONPATH=/tmp python -u /tmp/bake_models.py /tmp/stt.json

COPY stt-service/. .

CMD ["python", "main.py"]
