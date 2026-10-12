import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')  # Опционально

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
