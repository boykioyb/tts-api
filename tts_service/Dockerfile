# Build context is the REPO ROOT (see docker-compose.yml) so we can reach protos/.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/root/.cache/huggingface

# libsndfile for soundfile, ffmpeg for VieNeu's denoise/resample paths.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY tts_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY protos ./protos
COPY scripts/gen_protos.sh ./scripts/gen_protos.sh
COPY tts_service/app ./app

# Generate gRPC stubs into the app package.
RUN bash scripts/gen_protos.sh app/generated

EXPOSE 50051
CMD ["python", "-m", "app.server"]
