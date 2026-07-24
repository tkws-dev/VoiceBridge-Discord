# Discord Voice Bridge — Project Plan

## 🎯 Goal

True live AI voice conversation in Discord — voice-to-voice, <2s latency.

## 📊 Status

| Milestone | Status | Notes |
|-----------|--------|-------|
| Phase 1: Text→Voice (`!say`/`!ask`) | ✅ Done | gTTS + LLM, works 100% |
| Phase 2: Voice Pipeline (STT→LLM→TTS) | ⚡ v11 | Gemini-powered, ~5-10s |
| Phase 3: True Live Voice | 🔜 Next | Gemini Live or OpenAI Realtime |
| Phase 4: Production | 📋 Planned | Polish, deploy, monitor |

## 🔧 Phase 2 — Current (v11)

```
Discord Voice → Gemini STT → Gemini Flash LLM → gTTS TTS
                 1-2s          3-5s             0.5-2s
                          Total: ~5-10s
```

**Known Issues:**
- [ ] `discord-ext-voice_recv` alpha — opus/SSRC bugs need patching
- [ ] Free tier quota limited (1,500 req/day)
- [ ] STT accuracy varies with audio quality

## 🚀 Phase 3 — True Live Voice

### Option A: Gemini Multimodal Live (Recommended)
- WebSocket: `wss://generativelanguage.googleapis.com/...`
- Latency: <2s, true bidirectional, interrupt support
- Need: GOOGLE_API_KEY with billing
- Ref: https://ai.google.dev/gemini-api/docs/models/gemini-v2#live-api

### Option B: OpenAI Realtime API
- WebSocket: `wss://api.openai.com/v1/realtime`
- Latency: <500ms, superior quality
- Need: OPENAI_API_KEY
- Ref: https://platform.openai.com/docs/guides/realtime

## 📋 Backlog

- [ ] Gemini Live WebSocket bridge
- [ ] Stream audio directly (no save-to-file)
- [ ] Conversation context (multi-turn)
- [ ] Multiple speaker support
- [ ] Configurable wake word
- [ ] GPU-accelerated STT fallback (whisper.cpp)
- [ ] Docker deployment
- [ ] Health monitoring + auto-reconnect

## 🔑 Keys Needed

| Key | Source | Status |
|-----|--------|--------|
| GOOGLE_API_KEY | https://aistudio.google.com/apikey | ✅ Valid, needs billing |
| OPENAI_API_KEY | https://platform.openai.com/api-keys | ❌ Not yet |
| DISCORD_BOT_TOKEN | https://discord.com/developers | ✅ hermes-voice#0943 |

## 📂 Repository

```
discord-voice-bridge/
├── bridge_pipeline.py     # v11 Gemini pipeline (~5-10s)
├── bridge_gemini_live.py  # WIP: Gemini Live WebSocket (<2s)
├── setup.sh               # One-command install
├── requirements.txt       # Python deps
├── .env.example           # Env template
└── plan.md                # This file
```

## 📝 Lessons Learned (v1→v11)

1. DeepSeek v4 Pro = 30-60s — useless for live
2. GPT-4o-mini Thai sounds robotic — use GPT-4o or Gemini Flash
3. `discord-ext-voice_recv` has opus decoder bugs — must patch
4. Hermes CLI startup = 5-8s overhead — use direct API
5. faster-whisper `tiny` can't handle Thai — use `base` or cloud STT
6. gTTS Thai < 2s, Edge TTS Thai > 30s — stick with gTTS
7. One GOOGLE_API_KEY covers both STT and LLM — simpler is better

## 👥 Team

- @tikawutw (tkws) — Project owner
- Hermes Agent — AI development assistant

---

*Last updated: 2026-07-24 | v11*
