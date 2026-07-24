#!/usr/bin/env python3
"""Discord Voice Bridge v11 — Gemini-powered (STT + LLM via Google AI Studio)

Architecture inspired by OpenPud:
  Gemini STT → Gemini Flash LLM → gTTS TTS
  One API key, no Hermes CLI overhead, ~5-10s total

Usage:
    source venv/bin/activate
    python bridge_pipeline.py <voice_channel_id> <guild_id>
"""
import asyncio, os, sys, io, tempfile, subprocess, time, wave, re, json
from pathlib import Path
from collections import defaultdict

# ============================================================
# PATCH: discord-ext-voice_recv opus decoder bugs
# ============================================================
import discord.ext.voice_recv.opus as _opus
_orig = _opus.PacketDecoder._decode_packet
def _safe(self, packet):
    try: return _orig(self, packet)
    except: return (packet, b'')
_opus.PacketDecoder._decode_packet = _safe

import discord
from discord.ext import commands
from discord.ext.voice_recv import VoiceRecvClient, AudioSink, VoiceData
from gtts import gTTS

# ============================================================
# Config — single Gemini key for everything
# ============================================================
TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
GEMINI_KEY = os.environ.get('GOOGLE_API_KEY', '')
GEMINI_MODEL = 'gemini-2.0-flash'  # fast + free tier

VOICE_CH = int(sys.argv[1])
GUILD = int(sys.argv[2])

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)
vc = None

# ============================================================
# TTS: gTTS Thai (free, fast)
# ============================================================
def tts(text: str) -> bytes:
    if len(text) > 500: text = text[:500] + "..."
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f: mp = f.name
    gTTS(text, lang='th').save(mp)
    wp = mp + '.wav'
    subprocess.run(['ffmpeg', '-y', '-i', mp, '-ar', '48000', '-ac', '2',
        '-sample_fmt', 's16', wp], capture_output=True, timeout=10)
    with open(wp, 'rb') as f: d = f.read()
    os.unlink(mp); os.unlink(wp)
    return d

# ============================================================
# STT: Gemini Speech-to-Text (cloud, accurate Thai)
# ============================================================
def stt(pcm: bytes) -> str:
    """Send PCM audio to Gemini for transcription."""
    import base64, urllib.request, urllib.error
    
    # Convert PCM to WAV in memory
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(48000)
        wf.writeframes(pcm)
    audio_b64 = base64.b64encode(buf.getvalue()).decode()
    
    # Gemini speech-to-text via generateContent with audio
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    payload = json.dumps({
        "contents": [{
            "parts": [
                {"text": "Transcribe this audio in Thai. Output ONLY the Thai text, nothing else."},
                {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}}
            ]
        }]
    }).encode()
    
    try:
        req = urllib.request.Request(url, data=payload, 
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            # Clean: strip non-Thai
            return re.sub(r'\s+', ' ', text).strip()
    except Exception as e:
        print(f'  ⚠️ STT error: {e}')
        return ''

# ============================================================
# LLM: Gemini Flash (fast, natural Thai)
# ============================================================
async def llm(text: str) -> str:
    """One API call to Gemini for chat response."""
    import aiohttp
    
    prompt = f"""คุณคือผู้ช่วยเสียงภาษาไทย ตอบแบบธรรมชาติ สั้น ตรงประเด็น ใช้ภาษาพูด
ห้ามใช้ bullet points, markdown, หรือเครื่องหมายพิเศษ

ผู้ใช้พูดว่า: {text}

ตอบ:"""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 200}
            }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if 'candidates' in data:
                    return data['candidates'][0]['content']['parts'][0]['text'].strip()
                elif 'error' in data:
                    print(f'  ⚠️ LLM error: {data["error"]["message"][:100]}')
                    return ''
    except Exception as e:
        print(f'  ⚠️ LLM error: {e}')
        return ''

async def speak(audio: bytes):
    global vc
    if not vc or not vc.is_connected(): return
    s = discord.FFmpegPCMAudio(io.BytesIO(audio), pipe=True)
    vc.play(discord.PCMVolumeTransformer(s, volume=1.0))
    while vc.is_playing(): await asyncio.sleep(0.05)

# ============================================================
# Audio Sink — receives Discord voice, triggers on silence
# ============================================================
class Sink(AudioSink):
    def __init__(self):
        super().__init__()
        self.buf: dict[int, bytearray] = defaultdict(bytearray)
        self.last: dict[int, float] = {}
        self.proc: set[int] = set()
    def wants_opus(self) -> bool: return False

    def write(self, user, data: VoiceData):
        if user is None and data.pcm:
            if hasattr(self, '_vc'):
                for m in self._vc.channel.members:
                    if not m.bot: user = m; break
        if user is None or user.bot or not data.pcm: return
        self.buf[user.id].extend(data.pcm)
        self.last[user.id] = time.time()

    def cleanup(self): self.buf.clear(); self.last.clear()

    def start(self, loop):
        async def monitor():
            while True:
                await asyncio.sleep(0.5)
                now = time.time()
                for uid in list(self.buf):
                    if uid in self.proc: continue
                    if now - self.last.get(uid, 0) > 1.0 and len(self.buf[uid]) > 48000:
                        self.proc.add(uid)
                        asyncio.ensure_future(self._go(uid, bytes(self.buf[uid])))
                        self.buf[uid].clear()
        asyncio.ensure_future(monitor())

    async def _go(self, uid, pcm):
        try:
            t0 = time.time()
            txt = await asyncio.to_thread(stt, pcm)
            if not txt: return
            t1 = time.time(); print(f'📝 [{t1-t0:.1f}s]: {txt}')
            resp = await llm(txt)
            if not resp: return
            t2 = time.time(); print(f'🤖 [{t2-t1:.1f}s]: {resp[:100]}')
            await speak(await asyncio.to_thread(tts, resp))
            print(f'🔊 Total: {time.time()-t0:.1f}s')
        except Exception as e: print(f'❌ {e}')
        finally: self.proc.discard(uid)

# ============================================================
# Bot
# ============================================================
@bot.event
async def on_ready():
    global vc
    print(f'✅ v11 Gemini | {bot.user}')
    g = bot.get_guild(GUILD)
    ch = g.get_channel(VOICE_CH)
    vc = await ch.connect(cls=VoiceRecvClient)
    sink = Sink(); sink._vc = vc; vc.listen(sink); sink.start(asyncio.get_event_loop())
    print(f'🎤 {ch.name} | 🦻 Gemini STT + LLM + gTTS')
    await speak(tts("พร้อมครับ พูดมาเลย"))

@bot.command(name='say')
async def say(ctx, *, text: str):
    if not vc: return await ctx.send('❌')
    await speak(await asyncio.to_thread(tts, text))

@bot.command(name='ask')
async def ask(ctx, *, q: str):
    if not vc: return await ctx.send('❌')
    await ctx.send('🤔...')
    resp = await llm(q)
    if resp:
        await ctx.send(f'💬 {resp[:300]}')
        if vc.is_connected():
            await speak(await asyncio.to_thread(tts, resp))

if __name__ == '__main__':
    print('🎙️ v11 — Gemini STT + Gemini LLM + gTTS (~5-10s)')
    bot.run(TOKEN)
