# Integrate this TTS API into Auto-Create-Video

Auto-Create-Video already ships a LucyLab client (`src/tts/lucylab-client.ts`) that
speaks JSON-RPC. This gateway implements the same contract, so **integration is
configuration, not code** — you point the existing client at this gateway.

---

## Agent prompt (paste into an AI agent working in the Auto-Create-Video repo)

> You are integrating a local, self-hosted Vietnamese TTS service into this repo.
> The service exposes a **LucyLab-compatible JSON-RPC API**, so DO NOT write a new
> provider — reuse the existing `lucylab` provider and only change configuration.
>
> Do the following:
> 1. In `.env` (or `.env.local`), set:
>    ```
>    TTS_PROVIDER=lucylab
>    LUCYLAB_ENDPOINT=http://localhost:8600/json-rpc
>    VIETNAMESE_VOICEID=quang-anh
>    VIETNAMESE_API_KEY=local-no-auth      # any non-empty value; auth is disabled server-side
>    LUCYLAB_POLL_INTERVAL_MS=2000
>    LUCYLAB_POLL_TIMEOUT_MS=600000        # 10 min: survives model cold-start on first run
>    TTS_CONCURRENCY=1                     # the worker serializes inference
>    ```
> 2. Do NOT modify `lucylab-client.ts`, `tts-client.ts`, or the pipeline. The contract
>    matches: `ttsLongText` → `projectExportId`; `getExportStatus` → `{state,url,srtUrl}`.
> 3. Be aware the gateway returns `srtUrl: null` (no subtitles). The pipeline already
>    tolerates this (its ElevenLabs provider has no SRT either); scene `.srt` files just
>    won't be created. If burned-in captions are required, that is a separate task.
> 4. Verify with the "Smoke test" commands below BEFORE running the full pipeline.
> 5. Report back the voices list and one successful `ttsLongText` → poll → downloadable
>    `url` round-trip.

---

## Prerequisites

1. This `tts-api` is running and healthy:
   ```bash
   cd tts-api && cp .env.example .env && docker compose up --build
   ```
2. The voice you want exists. Check:
   ```bash
   curl -s http://localhost:8600/v1/voices | python3 -m json.tool
   ```
   You should see `"voice_id": "quang-anh"` (the enrolled clone) among the presets.

## What to configure in Auto-Create-Video

Only `.env` changes (see the agent prompt above). Key points, from first principles:

| Setting | Value | Why |
|---------|-------|-----|
| `LUCYLAB_ENDPOINT` | `http://localhost:8600/json-rpc` | redirect the existing client to this gateway |
| `VIETNAMESE_VOICEID` | `quang-anh` | the enrolled voice id (or any id from `/v1/voices`) |
| `VIETNAMESE_API_KEY` | any non-empty string | config validation requires it; the server ignores it |
| `LUCYLAB_POLL_TIMEOUT_MS` | `600000` | first request loads the model (minutes) — see cold-start |
| `TTS_CONCURRENCY` | `1` | the worker processes one clip at a time |

### Networking

- **Pipeline on host, gateway in Docker** (default): keep
  `http://localhost:8600` for both `LUCYLAB_ENDPOINT` and the gateway's own
  `GATEWAY_PUBLIC_BASE_URL`. The `url` returned by `getExportStatus` must be reachable
  by whoever downloads it (the pipeline) — `localhost:8600` works because the port is
  mapped.
- **Pipeline in the same Docker network**: set the gateway's
  `GATEWAY_PUBLIC_BASE_URL=http://gateway:8000` and the pipeline's
  `LUCYLAB_ENDPOINT=http://gateway:8000/json-rpc`, so the download `url` resolves inside
  the network.

### Cold start (important)

The first `ttsLongText` after boot triggers the model load (weight download + init,
several minutes). Two ways to avoid a poll timeout:

- **Warm up once** before running the pipeline (recommended):
  ```bash
  curl -s http://localhost:8600/v1/voices >/dev/null   # forces the worker to be ready
  ```
  The gateway only reports healthy after the model is loaded, so once `/v1/voices`
  returns, synthesis is fast (~seconds per scene).
- Or keep `LUCYLAB_POLL_TIMEOUT_MS` generous (600000).

## Smoke test (before the full pipeline)

```bash
# 1) submit
ID=$(curl -s -X POST http://localhost:8600/json-rpc -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"ttsLongText","input":{"text":"Xin chào, đây là bản tin công nghệ.","userVoiceId":"quang-anh","speed":1}}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["projectExportId"])')
echo "job: $ID"

# 2) poll until completed
curl -s -X POST http://localhost:8600/json-rpc -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":\"2\",\"method\":\"getExportStatus\",\"input\":{\"projectExportId\":\"$ID\"}}"

# 3) download the audio from the returned url
#    -> http://localhost:8600/files/<id>.mp3  (audio/mpeg)
```

Expected: state goes `processing` → `completed` with a `url`; `srtUrl` is `null`.

## Known differences vs the real LucyLab

- **No subtitles** — `srtUrl` is always `null`. VieNeu emits no timestamps; captions
  would need forced alignment. The pipeline skips SRT gracefully.
- **`speed` ignored** — only `1.0` is passed by the tool anyway.
- **In-memory jobs** — a gateway restart forgets in-flight jobs (fine for batch runs).
- **Auth disabled** — any `Authorization` header is accepted.

## Rollback

To switch back to the hosted LucyLab, restore in `.env`:
```
LUCYLAB_ENDPOINT=https://api.lucylab.io/json-rpc
VIETNAMESE_API_KEY=<your real key>
VIETNAMESE_VOICEID=<your lucylab voice id>
```
