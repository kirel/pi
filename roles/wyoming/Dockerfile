# Dockerfile
FROM wyoming-satellite:latest

# Install alsa-utils
RUN apt-get -y update && apt-get install -y alsa-utils pulseaudio-utils libasound2-plugins
RUN /app/.venv/bin/pip3 install 'pysilero-vad==1.0.0'
RUN /app/.venv/bin/pip3 install 'webrtc-noise-gain==1.2.3'
