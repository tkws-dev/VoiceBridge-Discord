# Discord Voice Bridge

Live voice-to-voice in Discord using AI — pipeline approach (STT→LLM→TTS) and WebSocket direct approach (Gemini Live).

## Project Structure

```
discord-voice-bridge/
├── README.md              # This file
├── bridge_pipeline.py     # Pipeline approach: STT → LLM → TTS
├── bridge_gemini_live.py  # Gemini Multimodal Live WebSocket bridge (recommended)
├── requirements.txt       # Python dependencies
├── SKILL.md               # Lessons learned & battle-tested workflow
└── .env.example           # Environment variables template
```

## Quick Start

### Method 1: Pipeline (STT → LLM → TTS)
```bash
cp .env.example .env
# Fill in DISCORD_BOT_TOKEN
pip install -r requirements.txt
python bridge_pipeline.py <voice_channel_id> <guild_id>
```

### Method 2: Gemini Live (⚡ Fast & True Live)
```bash
cp .env.example .env
# Fill in DISCORD_BOT_TOKEN + GOOGLE_API_KEY
pip install -r requirements.txt
python bridge_gemini_live.py <voice_channel_id> <guild_id>
```
