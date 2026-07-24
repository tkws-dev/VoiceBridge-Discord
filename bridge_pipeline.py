# Discord Voice Bridge — Pipeline Approach
# STT (faster-whisper) → LLM (GPT-4o via Codex) → TTS (gTTS)
# NOTE: ~20-30s latency. For true live voice, use bridge_gemini_live.py

import asyncio, os, sys, io, tempfile, subprocess, time, wave, re
from collections import defaultdict

# --- PATCH: workaround for discord-ext-voice_recv opus decode bugs ---
import discord.ext.voice_recv.opus as _opus
_orig_decode = _opus.PacketDecoder._decode_packet
def _safe_decode(self, packet):
    try: return _orig_decode(self, packet)
    except: return (packet, b'')
_opus.PacketDecoder._decode_packet = _safe_decode

import discord
from discord.ext import commands
from discord.ext.voice_recv import VoiceRecvClient, AudioSink, VoiceData
from gtts import gTTS

# --- Config ---
TOKEN = os.environ['DISCORD_BOT_TOKEN']
VOICE_CH = int(sys.argv[1])
GUILD = int(sys.argv[2])
VENV = os.path.expanduser('~/.hermes/hermes-agent/venv')

# --- Discord Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)
vc = None

# --- TTS: gTTS → WAV (Thai, fast) ---
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

# --- STT: faster-whisper base model (Thai) ---
def stt(pcm: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f: wp = f.name
    with wave.open(wp, 'wb') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(48000)
        wf.writeframes(pcm)
    r = subprocess.run([sys.executable, '-c', f'''
from faster_whisper import WhisperModel
m = WhisperModel("base", device="cpu", compute_type="int8")
s, _ = m.transcribe("{wp}", language="th", beam_size=1, best_of=1,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500))
print(" ".join(x.text for x in s))
'''], capture_output=True, text=True, timeout=15)
    os.unlink(wp)
    # Filter: keep only Thai chars + basic punctuation
    cleaned = re.sub(r'[^\u0E00-\u0E7F\u0E50-\u0E59\s.]', '', r.stdout.strip())
    return re.sub(r'\s+', ' ', cleaned).strip()

# --- LLM: GPT-4o via Hermes Codex (for best Thai quality) ---
async def llm(text: str) -> str:
    prompt = f"""ตอบแบบธรรมชาติ เป็นกันเอง สั้นๆ ตรงประเด็น ใช้ภาษาพูด

ผู้ใช้พูด: {text}
ตอบ:"""
    proc = await asyncio.create_subprocess_exec(
        f'{VENV}/bin/hermes', 'chat', '-q', prompt,
        '-m', 'gpt-4o', '--provider', 'openai-codex', '--quiet',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()

async def speak(audio: bytes):
    global vc
    if not vc or not vc.is_connected(): return
    s = discord.FFmpegPCMAudio(io.BytesIO(audio), pipe=True)
    vc.play(discord.PCMVolumeTransformer(s, volume=1.0))
    while vc.is_playing(): await asyncio.sleep(0.05)

# --- Audio Sink: buffers voice, triggers on silence ---
class Sink(AudioSink):
    def __init__(self):
        super().__init__()
        self.buf: dict[int, bytearray] = defaultdict(bytearray)
        self.last: dict[int, float] = {}
        self.proc: set[int] = set()
    def wants_opus(self) -> bool: return False

    def write(self, user, data: VoiceData):
        # Fallback: assign unknown SSRC to first human in channel
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
                    # 0.8s silence + 0.25s buffer = fast trigger
                    if now - self.last.get(uid, 0) > 0.8 and len(self.buf[uid]) > 24000:
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

# --- Bot Events ---
@bot.event
async def on_ready():
    global vc
    print(f'✅ {bot.user}')
    g = bot.get_guild(GUILD)
    ch = g.get_channel(VOICE_CH)
    vc = await ch.connect(cls=VoiceRecvClient)
    sink = Sink(); sink._vc = vc; vc.listen(sink); sink.start(asyncio.get_event_loop())
    print(f'🎤 {ch.name} | 🦻 Listening...')
    await speak(tts("พร้อมครับ พูดมาเลย"))

@bot.command(name='say')
async def say(ctx, *, text: str):
    if not vc: return await ctx.send('❌')
    await speak(await asyncio.to_thread(tts, text))

@bot.command(name='ask')
async def ask(ctx, *, q: str):
    if not vc: return await ctx.send('❌')
    resp = await llm(q)
    if vc and vc.is_connected():
        await speak(await asyncio.to_thread(tts, resp))

if __name__ == '__main__':
    print('🎙️ Voice Bridge — Pipeline Mode')
    bot.run(TOKEN)
