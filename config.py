import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# Проверяем, что все токены загружены
if not TELEGRAM_BOT_TOKEN:
    raise ValueError(" TELEGRAM_BOT_TOKEN не найден! Добавьте переменную в Railway.")
if not DISCORD_TOKEN:
    raise ValueError("❌ DISCORD_TOKEN не найден! Добавьте переменную в Railway.")
if not DISCORD_CHANNEL_ID:
    raise ValueError("❌ DISCORD_CHANNEL_ID не найден! Добавьте переменную в Railway.")

# Преобразуем ID канала в число
try:
    DISCORD_CHANNEL_ID = int(DISCORD_CHANNEL_ID)
except ValueError:
    raise ValueError(f"❌ DISCORD_CHANNEL_ID должен быть числом, а не '{DISCORD_CHANNEL_ID}'")

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
