#!/bin/bash
# Discord Voice Bridge — One-Command Setup
# Run: bash setup.sh
set -e

echo "🎙️ Discord Voice Bridge Setup"
echo "=============================="
echo ""

# 1. Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 not found. Install Python 3.10+"
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# 2. Check ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "❌ ffmpeg not found. Install: sudo apt install ffmpeg"
    exit 1
fi
echo "✅ ffmpeg: $(ffmpeg -version 2>&1 | head -1)"

# 3. Create venv
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Created venv"
fi
source venv/bin/activate

# 4. Install deps
pip install -q --upgrade pip
pip install -q discord.py[voice] gTTS faster-whisper discord-ext-voice_recv pydub
echo "✅ Dependencies installed"

# 5. Check .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Edit .env with your keys:"
    echo "   DISCORD_BOT_TOKEN=your_bot_token"
    echo "   GOOGLE_API_KEY=your_gemini_key   # for Gemini Live"
    echo ""
fi

# 6. Auto-detect Hermes (optional)
if [ -d "$HOME/.hermes/hermes-agent/venv" ]; then
    echo "✅ Hermes detected at ~/.hermes"
else
    echo "ℹ️  Hermes not detected — LLM will use GOOGLE_API_KEY directly"
fi

echo ""
echo "=============================="
echo "✅ Setup complete!"
echo ""
echo "Run pipeline mode:"
echo "  source venv/bin/activate"
echo "  python bridge_pipeline.py <voice_channel_id> <guild_id>"
echo ""
echo "Run Gemini Live (coming soon):"
echo "  python bridge_gemini_live.py <voice_channel_id> <guild_id>"
