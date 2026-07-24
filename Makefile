.PHONY: proto up down logs build rebuild clean

# Generate stubs locally (for IDE / running outside Docker).
proto:
	bash scripts/gen_protos.sh tts_service/app/generated
	bash scripts/gen_protos.sh gateway/app/generated

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

rebuild:
	docker compose build --no-cache

clean:
	rm -rf tts_service/app/generated gateway/app/generated
