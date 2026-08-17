# Используем официальный образ Python 3.10
FROM python:3.10.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    fonts-dejavu \
    fonts-liberation \
    fonts-ubuntu \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

# Создаем папку для временных файлов
RUN mkdir -p temp_images

# Команда запуска
CMD ["python", "bot.py"]
