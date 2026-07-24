# วิธียัดขึ้น GitHub

cd /home/tikawutw/workspace/discord-voice-bridge

# 1. สร้าง repo ใน GitHub: https://github.com/new
#    ชื่อ: discord-voice-bridge
#    (อย่าเติม README, .gitignore — เรามีแล้ว)

# 2. Push ขึ้น
git remote add origin https://github.com/tkws-dev/VoiceBridge-Discord.git
git push -u origin main

# หรือถ้ามี gh CLI
gh repo create discord-voice-bridge --public --source=. --push
