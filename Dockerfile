# Используем легкий образ Python
FROM python:3.11-slim

# Устанавливаем ffmpeg и очищаем кэш для экономии места
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код бота
COPY . .

# Команда для запуска бота
CMD ["python", "main.py"]
