import subprocess
import os
import sys
import time

print("🚀 Starting Discord Bot...")
# বটটাকে ব্যাকগ্রাউন্ডে রান করা হচ্ছে
subprocess.Popen([sys.executable, "bot.py"])

time.sleep(2) # ২ সেকেন্ড অপেক্ষা

print("🌐 Starting Flask Website...")
# ওয়েবসাইটটাকে ফোরগ্রাউন্ডে রান করা হচ্ছে (লগ সহ)
port = os.environ.get("PORT", "5000")
subprocess.call([
    sys.executable, "-m", "gunicorn", "app:app", 
    "-b", f"0.0.0.0:{port}", 
    "--access-logfile", "-", 
    "--error-logfile", "-"
])
