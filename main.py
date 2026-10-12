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
            "👋 Привет! Я конвертер GIF/анимаций.\n"
            "Отправь мне GIF или анимацию, и я конвертирую её в WebM для Discord!"
        )

    async def handle_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if config.TELEGRAM_CHAT_ID and str(update.effective_chat.id) != str(config.TELEGRAM_CHAT_ID):
            return

        message = update.message
        sender = message.from_user.first_name if message.from_user else "Unknown"

        try:
            # GIF-анимации (Telegram часто присылает их как MP4)
            if message.animation:
                logger.info(f"Получена анимация от {sender}")
                await update.message.reply_text(" Конвертирую в WebM...")
                await self._convert_and_send(message, context, sender, file_obj=message.animation)
            
            # Настоящие GIF файлы (документы)
            elif message.document and message.document.mime_type == 'image/gif':
                logger.info(f"Получен GIF-документ от {sender}")
                await update.message.reply_text("⏳ Конвертирую в WebM...")
                await self._convert_and_send(message, context, sender, file_obj=message.document)
            
            # Текст (ссылки и т.д.)
            elif message.text:
                logger.info(f"Получен текст от {sender}: {message.text}")
                content = f"**От:** {sender}\n\n{message.text}"
                self._send_to_discord_safe(content)

        except Exception as e:
            logger.error(f"Ошибка обработки: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

    async def _convert_and_send(self, message, context, sender, file_obj):
        """Скачивает файл, конвертирует в WebM и отправляет в Discord"""
        file = await context.bot.get_file(file_obj.file_id)
        
        # Определяем расширение входного файла
        file_name = file_obj.file_name or "animation"
        if file_name.lower().endswith('.gif'):
            input_ext = '.gif'
        else:
            input_ext = '.mp4'  # Telegram часто присылает анимации как MP4
        
        # Создаем временные файлы
        with tempfile.NamedTemporaryFile(suffix=input_ext, delete=False) as temp_input:
            input_path = temp_input.name
        
        output_path = input_path.replace(input_ext, '.webm')
        
        try:
            # Скачиваем файл
            logger.info(f"Скачиваю файл: {input_path}")
            await file.download_to_drive(input_path)
            
            # Проверяем размер
            file_size = os.path.getsize(input_path)
            logger.info(f"Размер файла: {file_size / 1024:.2f} KB")
            
            if file_size > 50 * 1024 * 1024:  # 50 MB
                raise Exception("Файл слишком большой (>50MB)")
            
            # Конвертируем в WebM
            logger.info(f"Конвертирую {input_ext} -> WebM")
            await self._convert_to_webm(input_path, output_path)
            
            # Отправляем в Discord
            with open(output_path, 'rb') as f:
                discord_file = discord.File(f, filename='converted.webm')
                content = f"**Анимация от:** {sender}"
                self._send_to_discord_safe(content, file=discord_file)
            
            logger.info("✅ Файл успешно конвертирован и отправлен")
            await message.reply_text("✅ Готово! Отправлено в Discord.")
            
        except Exception as e:
            logger.error(f"Ошибка конвертации: {e}", exc_info=True)
            raise
        finally:
            # Удаляем временные файлы
            for path in [input_path, output_path]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass

    async def _convert_to_webm(self, input_path, output_path):
        """Конвертирует файл в WebM используя ffmpeg"""
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libvpx-vp9',
            '-crf', '30',
            '-b:v', '0',
            '-quality', 'good',
            '-cpu-used', '4',
            '-an',
            '-y',
            output_path
        ]
        
        logger.info(f"Запуск: {' '.join(cmd)}")
        
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
        
        file_size = os.path.getsize(output_path)
        logger.info(f"WebM создан: {file_size / 1024:.2f} KB")

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
                logger.error(f"❌ Канал {config.DISCORD_CHANNEL_ID} не найден!")

    bot = DiscordBridgeBot()
    bot.run(config.DISCORD_TOKEN)


async def run_telegram_bot(bridge: BridgeBot):
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", bridge.start_command))
    
    # Принимаем анимации (GIF/MP4), GIF-документы и текст
    application.add_handler(
        MessageHandler(
            filters.ANIMATION | filters.Document.MimeType('image/gif') | filters.TEXT,
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
