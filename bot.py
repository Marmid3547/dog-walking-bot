from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Загружаем токен вашего бота из внешней конфигурации
TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'

# Вспомогательная функция для упрощения создания кнопок
def create_button(label, data):
    """Создает кнопку с текстом label и данным data."""
    return InlineKeyboardButton(label, callback_data=data)

# Главная функция старта бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Начальное сообщение с выбором основных действий.
    """
    buttons = [
        [create_button("Мой профиль", 'profile')],
        [create_button("Гулять с друзьями", 'friends')],
        [create_button("Найти локацию для прогулки", 'location')],
        [create_button("Найти ветклинику", 'vet_clinic')],
        [create_button("Найти зоомагазин", 'pet_shop')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text('Добро пожаловать!', reply_markup=reply_markup)

# Обработчик нажатий на кнопки
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатываем нажатия на кнопки и выдаем соответствующую реакцию.
    """
    query = update.callback_query
    await query.answer()

    if query.data == 'profile':
        # Переход в раздел "Профиль"
        profile_buttons = [
            [create_button("Где я гуляю", 'walk_location')],
            [create_button("Фото питомца", 'pet_photo')],
            [create_button("Назад", 'back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(profile_buttons)
        await query.edit_message_text(text="Ваш профиль:", reply_markup=reply_markup)

    elif query.data == 'friends':
        # Выбор друзей для прогулки
        friend_buttons = [
            [create_button("Написать другу", 'write_friend')],
            [create_button("Назад", 'back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(friend_buttons)
        await query.edit_message_text(text="Гулять с друзьями:", reply_markup=reply_markup)

    elif query.data == 'location':
        # Выбор места для прогулки
        location_buttons = [
            [create_button("Выбрать район", 'select_district')],
            [create_button("Выбрать локацию", 'select_place')],
            [create_button("Назад", 'back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(location_buttons)
        await query.edit_message_text(text="Найти локацию для прогулки:", reply_markup=reply_markup)

    else:
        # Общее уведомление о выполнении какого-то действия
        await query.edit_message_text(text=f"Выполняется действие {query.data}")

# Главная точка входа
def main():
    """
    Запускает бота и добавляет обработчики событий.
    """
    application = ApplicationBuilder().token(TOKEN).build()

    # Добавляем обработчики команд и кнопок
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))

    # Начинаем прослушивать сообщения
    print("Bot started!")
    application.run_polling()

# Точка входа программы
if __name__ == '__main__':
    main()
