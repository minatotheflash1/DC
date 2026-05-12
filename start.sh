python bot.py &
gunicorn app:app -b 0.0.0.0:$PORT
