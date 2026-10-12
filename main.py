import asyncio
import logging
import threading
import io
import os
import tempfile
import subprocess
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
            "👋 Привет! Я конвертер GIF.\n"
            "Отправь мне GIF, и я конвертирую её в WebM для Discord!"
        )

    async def handle_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if config.TELEGRAM_CHAT_ID and str(update.effective_chat.id) != str(config.TELEGRAM_CHAT_ID):
            return

        message = update.message
        sender = message.from_user.first_name if message.from_user else "Unknown"

        try:
            # Проверяем, есть ли GIF/анимация
            if message.animation or (message.document and message.document.mime_type == 'image/gif'):
                logger.info(f"Получена GIF от {sender}")
                await update.message.reply_text("⏳ Конвертирую GIF в WebM...")
                await self._convert_and_send_gif(message, context, sender)
            
            elif message.text:
                logger.info(f"Получен текст от {sender}: {message.text}")
                content = f"**От:** {sender}\n\n{message.text}"
                self._send_to_discord_safe(content)

        except Exception as e:
            logger.error(f"Ошибка обработки: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

    async def _convert_and_send_gif(self, message, context, sender):
        """Скачивает GIF, конвертирует в WebM и отправляет в Discord"""
        file_obj = message.animation or message.document
        file = await context.bot.get_file(file_obj.file_id)
        
        # Создаем временные файлы
        with tempfile.NamedTemporaryFile(suffix='.gif', delete=False) as temp_gif:
            gif_path = temp_gif.name
        
        webm_path = gif_path.replace('.gif', '.webm')
        
        try:
            # Скачиваем GIF
            logger.info(f"Скачиваю GIF: {gif_path}")
            await file.download_to_drive(gif_path)
            
            # Конвертируем в WebM через ffmpeg
            logger.info(f"Конвертирую в WebM: {webm_path}")
            await self._convert_gif_to_webm(gif_path, webm_path)
            
            # Отправляем в Discord
            with open(webm_path, 'rb') as f:
                discord_file = discord.File(f, filename='converted.webm')
                content = f"**GIF от:** {sender}"
                self._send_to_discord_safe(content, file=discord_file)
            
            logger.info("✅ GIF успешно конвертирована и отправлена")
            
        except Exception as e:
            logger.error(f"Ошибка конвертации: {e}", exc_info=True)
            raise
        finally:
            # Удаляем временные файлы
            for path in [gif_path, webm_path]:
                if os.path.exists(path):
                    os.remove(path)

    async def _convert_gif_to_webm(self, input_path, output_path):
        """Конвертирует GIF в WebM используя ffmpeg"""
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libvpx-vp9',
            '-crf', '30',
            '-b:v', '0',
            '-quality', 'good',
            '-cpu-used', '4',
            '-an',  # без аудио
            '-y',   # перезаписать если существует
            output_path
        ]
        
        logger.info(f"Запуск ffmpeg: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
            logger.error(f"ffmpeg ошибка: {error_msg}")
            raise Exception(f"Ошибка конвертации: {error_msg[:200]}")
        
        # Проверяем размер файла
        file_size = os.path.getsize(output_path)
        logger.info(f"WebM создан: {file_size / 1024:.2f} KB")
        
        if file_size > 50 * 1024 * 1024:  # 50 MB
            raise Exception("Файл слишком большой (>50MB)")

    def _send_to_discord_safe(self, content, file=None):
        """Безопасная отправка в Discord из потока Telegram"""
        if not self.discord_channel or not self.discord_loop:
            logger.warning("Discord канал или loop еще не инициализирован")
            return

        async def _send():
            try:
                if file:
                    await self.discord_channel.send(content=content, file=file)
                else:
                    await self.discord_channel.send(content=content)
                logger.info("✅ Успешно отправлено в Discord")
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
                logger.error(f" Канал {config.DISCORD_CHANNEL_ID} не найден!")

    bot = DiscordBridgeBot()
    bot.run(config.DISCORD_TOKEN)


async def run_telegram_bot(bridge: BridgeBot):
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", bridge.start_command))
    
    # Принимаем GIF (animation), документы и текст
    application.add_handler(
        MessageHandler(
            filters.ANIMATION | filters.Document.ALL | filters.TEXT,
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
    logger.info("🚀 Запуск GIF конвертера Telegram -> Discord")
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
