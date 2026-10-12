# Telegram to Discord Bridge

Простой бот для пересылки сообщений из Telegram в Discord.

## Как это работает

1. Пользователь отправляет сообщение (ссылку на твитер с GIF) в Telegram бот
2. Бот пересылает сообщение в указанный Discord канал
3. Другой бот/сервис в Discord скачивает и конвертирует GIF

## Настройка

### 1. Создайте Telegram бота
- Напишите [@BotFather](https://t.me/botfather)
- Команда `/newbot`
- Скопируйте токен

### 2. Создайте Discord бота
- [Discord Developer Portal](https://discord.com/developers/applications)
- Создайте приложение → Bot
- Скопируйте токен
- Включите нужные intents
- Пригласите бота на сервер

### 3. Получите ID Discord канала
- В Discord включите режим разработчика (Настройки → Дополнительно)
- ПКМ на канале → "Копировать ID"

### 4. Настройте .env
```env
TELEGRAM_BOT_TOKEN=your_telegram_token
DISCORD_TOKEN=your_discord_token
DISCORD_CHANNEL_ID=1234567890123456789
