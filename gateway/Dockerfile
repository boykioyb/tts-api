# Build context is the REPO ROOT (see docker-compose.yml) so we can reach protos/.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY protos ./protos
COPY scripts/gen_protos.sh ./scripts/gen_protos.sh
COPY gateway/app ./app

RUN bash scripts/gen_protos.sh app/generated

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
