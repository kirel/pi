# Home ASR streaming

Endpoint: `wss://litellm.kirelabs.org/v1/realtime?model=home-asr-stream`

Authenticate with `Authorization: Bearer <LiteLLM key>`. The key and its team
must allow `home-asr-stream`; permission for `home-asr` alone does not grant it.
LiteLLM forwards the WebSocket to CrispASR's JSON Realtime listener on
`ailab-ubuntu.lan:10303`. That listener is bound to the LAN address, without
backend authentication, like the existing local inference endpoints. External
clients should use the authenticated TLS endpoint above.

Send **16 kHz, mono, signed little-endian PCM16**, without WAV headers:

```json
{"type":"input_audio_buffer.append","audio":"<base64 PCM16 chunk>"}
```

Send chunks continuously (for example, one second each). Finish an utterance:

```json
{"type":"input_audio_buffer.commit"}
```

Responses include `session.created`,
`conversation.item.input_audio_transcription.delta` (`delta`), and
`conversation.item.input_audio_transcription.completed` (`transcript`).

This is CrispASR 0.8.23's limited Realtime protocol, not the full OpenAI Realtime
session API:

- Whisper repeatedly transcribes the accumulated audio; language is German.
- Partial `delta` events can contain replacements or repeats, without a flag
  distinguishing them from suffixes. Do not concatenate them into the final
  transcript. Use `completed.transcript` as the authoritative result.
- There is no server VAD or session configuration acknowledgement. Clients
  must commit utterances themselves; the backend also commits above 30 seconds.
- The server does not implement WebSocket ping/pong; the test disables pings.
- The existing `home-asr` HTTP file-upload endpoint still returns a complete
  response, including when passed `stream=true`.

Run the live check with a spoken 16 kHz mono PCM16 WAV and `LITELLM_API_KEY`
already set securely in the environment:

```bash
uv run --with websockets scripts/test_asr_stream.py speech.wav
```

The check requires text before commit and a nonempty completed transcript.
On 2026-09-25, the direct backend and the authenticated LiteLLM TLS route each
returned 11 partial events before commit for an 11-second public speech sample.
Unauthenticated access and a key limited to `home-tts` were rejected.

Sources: [LiteLLM Realtime proxy](https://docs.litellm.ai/docs/realtime),
[CrispASR server](https://github.com/CrispStrobe/CrispASR/blob/main/docs/server.md).

## TTS streaming through LiteLLM

`POST https://litellm.kirelabs.org/v1/audio/speech/stream` is a native,
authenticated LiteLLM passthrough configured in Ansible. No software patches.
It forwards to llama-swap's fixed Qwen3-TTS upstream, which starts on demand.
The regular `/v1/audio/speech` endpoint retains its buffered behavior.

All eight Hermes keys can use this endpoint through their six teams' explicit
`metadata.allowed_passthrough_routes` grant. A `home-tts` model grant alone
does not authorize this extra route. STT retains its separate
`home-asr-stream` model permission.

With `LITELLM_API_KEY` already set securely:

```bash
curl --fail-with-body --no-buffer \
  https://litellm.kirelabs.org/v1/audio/speech/stream \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"home-tts","voice":"de-host","input":"Hallo, hier beginnt die Sprachausgabe. Weitere Audiodaten folgen während der Erzeugung.","response_format":"pcm","stream":true}' \
  --output speech.pcm
```

The response is raw **24 kHz mono PCM16 little-endian**, `Content-Type: audio/pcm`.
Clients can play arriving bytes immediately, instead of waiting for EOF.
The entire input text is sent in one request; streaming refers to audio output.
Use `response_format: pcm` and `stream: true`; compressed formats such as MP3
are not supported by CrispASR's streaming mode.

On 2026-09-25, the TLS route returned first audio at 0.22 seconds and continued
until 3.44 seconds (583680 bytes). Unauthenticated requests returned 401, and a
key with `home-tts` but no passthrough route grant returned 403.

Source: [LiteLLM configurable passthrough](https://docs.litellm.ai/docs/proxy/pass_through).
The installed version supports authenticated routes in OSS; older documentation
still labels the `auth` setting Enterprise-only.
