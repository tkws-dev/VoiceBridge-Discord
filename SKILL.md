---
name: discord-voice-bridge
description: Build live AI voice bots in Discord — pipeline (STT→LLM→TTS) and Gemini Live WebSocket approaches. Covers opus decoder patching, SSRC handling, Thai TTS/STT, and production-hardened patterns.
category: voice
---

# Discord Voice Bridge — Battle-Tested Workflow

Build an AI voice bot that listens and speaks in Discord voice channels. Two approaches: **(A) Pipeline** (STT → LLM → TTS, ~20-30s) and **(B) Gemini Live WebSocket** (<2s, true bidirectional).

## When to Use

- User wants a Discord bot that can join voice channels, hear speech, and respond with AI
- User wants voice-to-voice interaction (not just text→voice)
- User is on WSL (no local audio device) and needs server-side audio processing

## Approach A: Pipeline (STT → LLM → TTS)

**Works today. ~20-30s total latency. Not truly "live" but functional.**

## Architecture v11 (Gemini-Powered)

```
Discord Voice → Gemini STT (cloud) → Gemini Flash LLM → gTTS TTS → Discord Voice
                    1-2s                 3-5s           0.5-2s
                              Total: ~5-10s (3x faster!)
```

**One API key, zero local dependencies for STT/LLM.**

### Why This Architecture (inspired by OpenPud)

| Our Old | New | Improvement |
|---------|-----|-------------|
| faster-whisper `base` (local CPU) | Gemini STT (cloud GPU) | 3x faster, more accurate Thai |
| Hermes CLI → GPT-4o | Gemini Flash direct API | No 5-8s overhead |
| Multiple credentials | One GOOGLE_API_KEY | Simpler setup |
### Prerequisites

1. **Discord Bot** with Privileged Intents:
   - MESSAGE CONTENT INTENT (Developer Portal → Bot → enable it!)
   - Server Members Intent
   - Invite with permissions: `36768768` (Connect, Speak, Read Messages)

2. **Python venv** with:
   ```bash
   pip install discord.py[voice] gTTS faster-whisper discord-ext-voice_recv
   ```

3. **ffmpeg** installed (for audio conversion)
4. **Hermes** with Codex OAuth credential (for GPT-4o via Codex)

### Critical Patches (NON-NEGOTIABLE)

These 3 patches are REQUIRED for the pipeline to work:

#### 1. Opus Decoder Error Handler
```python
import discord.ext.voice_recv.opus as _opus
_orig = _opus.PacketDecoder._decode_packet
def _safe(self, packet):
    try: return _orig(self, packet)
    except: return (packet, b'')
_opus.PacketDecoder._decode_packet = _safe
```
**Why:** The voice_recv alpha library encounters corrupted Opus packets from Discord. Without this patch, the PacketRouter thread crashes and stops delivering ALL audio. The patch silently drops bad packets.

#### 2. SSRC Fallback Mapping
```python
def write(self, user, data: VoiceData):
    if user is None and data.pcm:
        for m in self._vc.channel.members:
            if not m.bot: user = m; break
```
**Why:** Discord assigns SSRC (synchronization source) IDs to each speaker. If the SSRC→user mapping isn't established before audio packets arrive, voice_recv delivers packets with `user=None`. The sink must fallback to the first human in the channel.

#### 3. LLM Call via Hermes CLI
```python
async def llm(text: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        f'{VENV}/bin/hermes', 'chat', '-q', prompt,
        '-m', 'gpt-4o', '--provider', 'openai-codex', '--quiet',
        stdout=..., stderr=...)
    stdout, _ = await proc.communicate()
    return stdout.decode()
```
**Why:** Hermes CLI via Codex OAuth is the only free way to call GPT-4o. Direct OpenAI API needs a paid key. The `--quiet` flag is critical to avoid extra output.

### Thai-Specific Optimizations

| Component | Choice | Why |
|-----------|--------|-----|
| STT Model | faster-whisper `base` | `tiny` too inaccurate for Thai; `base` is the sweet spot |
| STT Filter | `re.sub(r'[^\u0E00-\u0E7F\s.]', '', text)` | Whisper hallucinates symbols — strip non-Thai chars |
| VAD | `vad_filter=True, min_silence_duration_ms=500` | Prevent ghost transcriptions from silence |
| TTS | gTTS (`lang='th'`) | ~0.5-2s, free; Edge TTS is 30s+ for Thai |
| LLM | gpt-4o (not mini) | Mini's Thai sounds robotic; 4o is natural |
| Prompt | "ตอบแบบธรรมชาติ เป็นกันเอง ภาษาพูด" | Without this, responses are formal/robotic |

### WSL-Specific Notes

- No local audio device — all processing is server-side
- `LD_LIBRARY_PATH` may need to exclude broken libopus in venv
- `ffmpeg` handles all format conversions (mp3↔wav, opus↔pcm)
- If opus decode errors persist, try `opuslib` pip package for correct libopus

### Known Issues & Mitigations

| Issue | Symptom | Fix |
|-------|---------|-----|
| PacketRouter crash | "OpusError: corrupted stream", then no more audio | Opus decode patch (#1) |
| Unknown SSRC | "Received packet for unknown ssrc" — packets silently dropped | SSRC fallback (#2) |
| gTTS clipping | Audio cuts off mid-sentence | Truncate input to 500 chars before TTS |
| Hermes CLI slow | 5-8s startup overhead per call | Use direct API call instead of CLI |
| STT gibberish | "ผน ขึ้นกับ คุณ ราษาจริง THAT" | Thai filter + VAD |

### Total Latency Breakdown
```
Audio buffer:      0.8s (silence detection)
STT (Whisper):     3-5s
Hermes CLI start:  5-8s
GPT-4o response:   8-15s
TTS (gTTS):       0.5-2s
───────────────────────
Total:           ~17-30s
```
**→ NOT suitable for real-time conversation. Use Approach B for live voice.**

---

## Approach B: Gemini Multimodal Live (RECOMMENDED)

**True bidirectional voice. <2s latency. WebSocket direct to Gemini.**

### Why Gemini Live

- **No STT → LLM → TTS pipeline** — audio goes directly to Gemini
- **WebSocket streaming** — responses arrive as they're generated
- **True bidirectional** — interrupt while speaking, like a phone call
- **Free tier available** — GOOGLE_API_KEY from Google AI Studio
- **Thai quality** — better than GPT-4o-mini, comparable to GPT-4o

### Architecture (Planned)
```
Discord Voice → PCM Audio → WebSocket → Gemini Live → PCM Audio → Discord Voice
```

### Requirements
- `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com)
- `DISCORD_BOT_TOKEN` (separate bot from hermes-tkws recommended)
- WebSocket bridge script (bridge_gemini_live.py — WIP)

### Key Differences from Pipeline

| | Pipeline | Gemini Live |
|---|---|---|
| Latency | 20-30s | <2s |
| Components | 4 separate (STT+LLM+TTS+Hermes) | 1 (Gemini WS) |
| Audio quality | Encoded→decoded→encoded | Native |
| Interrupt handling | None | Built-in |
| Cost | Free (Codex) | Free tier available |

---

## Bot Setup Checklist

1. [ ] Create Discord Application at https://discord.com/developers
2. [ ] Enable **MESSAGE CONTENT INTENT** (Privileged Gateway Intents)
3. [ ] Enable **SERVER MEMBERS INTENT**
4. [ ] Invite bot with permissions `36768768`
5. [ ] Set `DISCORD_BOT_TOKEN` in `.env`
6. [ ] For Gemini: set `GOOGLE_API_KEY` in `.env`
7. [ ] Copy bot to server, give it Connect + Speak permissions

## Testing

```bash
# In Discord text channel:
!say สวัสดีครับ          # Test TTS only
!ask OmniHub มีกี่ออเดอร์  # Test LLM → TTS

# In voice channel:
# Just speak — bot listens and responds (pipeline mode)
```

## File Reference

- `bridge_pipeline.py` — Full working pipeline (Approach A)
- `bridge_gemini_live.py` — Gemini Live bridge (Approach B, WIP)
- Running instance: `/home/tikawutw/.hermes/scripts/discord_voice_bridge.py`
- Hermes venv: `/home/tikawutw/.hermes/hermes-agent/venv/`

## Key Credentials (from this session)

| Credential | Provider | Source |
|------------|----------|--------|
| `DISCORD_VOICE_BOT_TOKEN` | Discord | `.env` — bot `hermes-voice#0943` |
| `GOOGLE_API_KEY` | Gemini | `.env` |
| `openai-codex-oauth-1` | OpenAI Codex | `hermes auth` — GPT-4o access |
