import asyncio
import logging
import threading
from telegram import Update, InputFile
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import discord
from discord.ext import commands
import config
import io

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BridgeBot:
    """Мост между Telegram и Discord"""
    
    def __init__(self):
        self.discord_channel = None
        self.telegram_app = None
    
    async def handle_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений из Telegram"""
        
        # Если указан конкретный чат, проверяем его
        if config.TELEGRAM_CHAT_ID:
            if str(update.effective_chat.id) != config.TELEGRAM_CHAT_ID:
                return
        
        message = update.message
        
        # Проверяем тип сообщения
        if message.video:
            # Видео файл
            await self._forward_video(message, context)
        elif message.document:
            # Документ (может быть видео)
            if message.document.mime_type.startswith('video/'):
                await self._forward_document(message, context)
        elif message.photo:
            # Фото
            await self._forward_photo(message, context)
        elif message.text:
            # Текст (например, ссылка на твитер)
            await self._forward_text(message)
    
    async def _forward_video(self, message, context):
        """Пересылает видео из Telegram в Discord"""
        try:
            logger.info(f"Получено видео от {message.from_user.first_name}")
            
            # Получаем файл
            file = await context.bot.get_file(message.video.file_id)
            
            # Скачиваем в память
            file_bytes = io.BytesIO()
            await file.download_to_memory(file_bytes)
            file_bytes.seek(0)
            
            # Отправляем в Discord
            if self.discord_channel:
                discord_file = discord.File(file_bytes, filename=f"video_{message.video.file_unique_id}.mp4")
                
                caption = message.caption or ""
                if message.from_user:
                    caption = f"**От:** {message.from_user.first_name}\n{caption}"
                
                await self.discord_channel.send(content=caption, file=discord_file)
                logger.info("✅ Видео отправлено в Discord")
            
        except Exception as e:
            logger.error(f"Ошибка пересылки видео: {e}", exc_info=True)
    
    async def _forward_document(self, message, context):
        """Пересылает документ (видео) из Telegram в Discord"""
        try:
            logger.info(f"Получен документ от {message.from_user.first_name}")
            
            file = await context.bot.get_file(message.document.file_id)
            
            file_bytes = io.BytesIO()
            await file.download_to_memory(file_bytes)
            file_bytes.seek(0)
            
            if self.discord_channel:
                filename = message.document.file_name or "file.mp4"
                discord_file = discord.File(file_bytes, filename=filename)
                
                caption = message.caption or ""
                if message.from_user:
                    caption = f"**От:** {message.from_user.first_name}\n{caption}"
                
                await self.discord_channel.send(content=caption, file=discord_file)
                logger.info("✅ Документ отправлен в Discord")
            
        except Exception as e:
            logger.error(f"Ошибка пересылки документа: {e}", exc_info=True)
    
    async def _forward_photo(self, message, context):
        """Пересылает фото из Telegram в Discord"""
        try:
            logger.info(f"Получено фото от {message.from_user.first_name}")
            
            # Берем фото лучшего качества
            photo = message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            
            file_bytes = io.BytesIO()
            await file.download_to_memory(file_bytes)
            file_bytes.seek(0)
            
            if self.discord_channel:
                discord_file = discord.File(file_bytes, filename=f"photo_{photo.file_unique_id}.jpg")
                
                caption = message.caption or ""
                if message.from_user:
                    caption = f"**От:** {message.from_user.first_name}\n{caption}"
                
                await self.discord_channel.send(content=caption, file=discord_file)
                logger.info("✅ Фото отправлено в Discord")
            
        except Exception as e:
            logger.error(f"Ошибка пересылки фото: {e}", exc_info=True)
    
    async def _forward_text(self, message):
        """Пересылает текст из Telegram в Discord"""
        try:
            logger.info(f"Получен текст от {message.from_user.first_name}")
            
            if self.discord_channel:
                sender = message.from_user.first_name if message.from_user else "Unknown"
                content = f"**От:** {sender}\n\n{message.text}"
                
                await self.discord_channel.send(content=content)
                logger.info("✅ Текст отправлен в Discord")
            
        except Exception as e:
            logger.error(f"Ошибка пересылки текста: {e}", exc_info=True)


def run_discord_bot(bridge: BridgeBot):
    """Запускает Discord бота и сохраняет канал"""
    
    class DiscordBridgeBot(commands.Bot):
        def __init__(self):
            intents = discord.Intents.default()
            super().__init__(command_prefix='!', intents=intents)
            self.bridge = bridge
        
        async def on_ready(self):
            logger.info(f"Discord бот запущен как {self.user}")
            
            # Получаем канал
            channel = self.get_channel(config.DISCORD_CHANNEL_ID)
            if channel:
                self.bridge.discord_channel = channel
                logger.info(f"✅ Канал Discord найден: #{channel.name}")
            else:
                logger.error(f"❌ Канал {config.DISCORD_CHANNEL_ID} не найден!")
    
    bot = DiscordBridgeBot()
    bot.run(config.DISCORD_TOKEN)


async def run_telegram_bot(bridge: BridgeBot):
    """Запускает Telegram бота"""
    
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчик всех сообщений
    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
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
    """Главная функция"""
    logger.info("🚀 Запуск моста Telegram -> Discord")
    
    bridge = BridgeBot()
    
    # Запускаем Discord в отдельном потоке
    discord_thread = threading.Thread(
        target=run_discord_bot, 
        args=(bridge,),
        daemon=True
    )
    discord_thread.start()
    
    # Ждем пока Discord подключится
    await asyncio.sleep(3)
    
    # Запускаем Telegram
    await run_telegram_bot(bridge)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
