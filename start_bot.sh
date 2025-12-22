#!/bin/bash
# Скрипт для запуска бота через PM2

cd "$(dirname "$0")"

# Создаем директорию для логов, если её нет
mkdir -p logs

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "Ошибка: файл .env не найден!"
    echo "Создайте файл .env с переменными BOT_TOKEN и ADMIN_ID"
    exit 1
fi

# Запускаем или перезапускаем бота через PM2
if pm2 list | grep -q "bot"; then
    echo "Перезапускаем существующий процесс bot..."
    pm2 restart bot
else
    echo "Запускаем новый процесс bot..."
    pm2 start bot.py --name bot --interpreter python3
fi

# Сохраняем список процессов
pm2 save

echo "Бот запущен! Для просмотра логов используйте: pm2 logs bot"
echo "Для остановки: pm2 stop bot"
echo "Для перезапуска: pm2 restart bot"
