import asyncio
import logging
import threading
import io
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
import discord
from discord.ext import commands
import config

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BridgeBot:
    def __init__(self):
        self.discord_channel = None
        self.discord_loop = None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Привет! Я мост между Telegram и Discord.\n"
            "Отправь мне ссылку, GIF, видео, фото или текст, и я перешлю это в Discord!"
        )

    async def handle_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if config.TELEGRAM_CHAT_ID and str(update.effective_chat.id) != str(config.TELEGRAM_CHAT_ID):
            return

        message = update.message
        sender = message.from_user.first_name if message.from_user else "Unknown"

        try:
            if message.text:
                logger.info(f"Получен текст от {sender}")
                content = f"**От:** {sender}\n\n{message.text}"
                self._send_to_discord_safe(content)

            # 1. Обработка GIF (анимаций)
            elif message.animation or (message.document and message.document.mime_type == 'image/gif'):
                logger.info(f"Получена GIF от {sender}")
                await self._forward_gif(message, context, sender)

            # 2. Обработка обычных видео
            elif message.document and message.document.mime_type.startswith('video/'):
                logger.info(f"Получен видео-документ от {sender}")
                await self._forward_media(message, context, sender, is_document=True)
            elif message.video:
                logger.info(f"Получено видео от {sender}")
                await self._forward_media(message, context, sender, is_document=False)

            # 3. Обработка фото
            elif message.photo:
                logger.info(f"Получено фото от {sender}")
                await self._forward_photo(message, context, sender)

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}", exc_info=True)

    async def _forward_gif(self, message, context, sender):
        """Специальная обработка для GIF, чтобы Discord показал их как анимацию"""
        file_obj = message.animation or message.document
        file = await context.bot.get_file(file_obj.file_id)
        
        file_bytes = io.BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)
        
        # ХИТРОСТЬ: Принудительно меняем расширение на .gif, чтобы Discord отобразил его как анимацию
        original_name = file_obj.file_name or "animation.mp4"
        if not original_name.lower().endswith('.gif'):
            filename = "animation.gif"
        else:
            filename = original_name
            
        caption = message.caption or ""
        content = f"**От:** {sender}\n{caption}"
        
        discord_file = discord.File(file_bytes, filename=filename)
        self._send_to_discord_safe(content, file=discord_file)

    async def _forward_media(self, message, context, sender, is_document=False):
        file_obj = message.document if is_document else message.video
        file = await context.bot.get_file(file_obj.file_id)
        
        file_bytes = io.BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)
        
        filename = file_obj.file_name if is_document else f"video_{file_obj.file_unique_id}.mp4"
        caption = message.caption or ""
        content = f"**От:** {sender}\n{caption}"
        
        discord_file = discord.File(file_bytes, filename=filename)
        self._send_to_discord_safe(content, file=discord_file)

    async def _forward_photo(self, message, context, sender):
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        file_bytes = io.BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)
        
        caption = message.caption or ""
        content = f"**От:** {sender}\n{caption}"
        
        discord_file = discord.File(file_bytes, filename=f"photo_{photo.file_unique_id}.jpg")
        self._send_to_discord_safe(content, file=discord_file)

    def _send_to_discord_safe(self, content, file=None):
        if not self.discord_channel or not self.discord_loop:
            logger.warning("Discord канал или loop еще не инициализирован")
            return

        async def _send():
            try:
                if file:
                    await self.discord_channel.send(content=content, file=file)
                else:
                    await self.discord_channel.send(content=content)
            except Exception as e:
                logger.error(f"Ошибка отправки в Discord: {e}")

        asyncio.run_coroutine_threadsafe(_send(), self.discord_loop)


def run_discord_bot(bridge: BridgeBot):
    class DiscordBridgeBot(commands.Bot):
        def __init__(self):
            intents = discord.Intents.default()
            intents.message_content = True
            super().__init__(command_prefix='!', intents=intents)
            self.bridge = bridge

        async def on_ready(self):
            logger.info(f"Discord бот запущен как {self.user}")
            self.bridge.discord_channel = self.get_channel(config.DISCORD_CHANNEL_ID)
            self.bridge.discord_loop = self.loop
            
            if self.bridge.discord_channel:
                logger.info(f"✅ Канал Discord найден: #{self.bridge.discord_channel.name}")
            else:
                logger.error(f"❌ Канал {config.DISCORD_CHANNEL_ID} не найден!")

    bot = DiscordBridgeBot()
    bot.run(config.DISCORD_TOKEN)


async def run_telegram_bot(bridge: BridgeBot):
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", bridge.start_command))
    
    # ДОБАВЛЕНО: filters.ANIMATION для перехвата GIF из встроенного поиска Telegram
    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.ANIMATION,
            bridge.handle_telegram_message
        )
    )
    
    logger.info("Запуск Telegram бота...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await application.stop()
        await application.shutdown()


async def main():
    logger.info("🚀 Запуск моста Telegram -> Discord")
    bridge = BridgeBot()
    
    discord_thread = threading.Thread(target=run_discord_bot, args=(bridge,), daemon=True)
    discord_thread.start()
    
    await asyncio.sleep(3)
    await run_telegram_bot(bridge)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
