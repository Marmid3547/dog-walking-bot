import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен бота из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Убедитесь, что вы создали .env файл с токеном.")

# Состояния для ConversationHandler
WAITING_LOCATION, WAITING_FRIEND_NAME, WAITING_DISTRICT, WAITING_LOCATION_CHOICE = range(4)

# Хранение данных пользователей (в реальном проекте лучше использовать БД)
user_data = {}


def get_main_menu():
    """Создает главное меню с 5 кнопками"""
    keyboard = [
        [InlineKeyboardButton("Мой профиль", callback_data="profile")],
        [InlineKeyboardButton("Гулять с друзьями", callback_data="walk_with_friends")],
        [InlineKeyboardButton("Найти локацию для прогулки", callback_data="find_location")],
        [InlineKeyboardButton("Найти ветклинику", callback_data="find_vet")],
        [InlineKeyboardButton("Найти зоомагазин", callback_data="find_pet_shop")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_profile_menu():
    """Создает меню профиля"""
    keyboard = [
        [InlineKeyboardButton("Где я гуляю", callback_data="my_walking_location")],
        [InlineKeyboardButton("Фото питомца", callback_data="pet_photo")],
        [InlineKeyboardButton("Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_walking_location_menu():
    """Меню для редактирования локации прогулок"""
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="profile")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_walk_with_friends_menu():
    """Меню для прогулок с друзьями"""
    keyboard = [
        [InlineKeyboardButton("Написать другу", callback_data="write_friend")],
        [InlineKeyboardButton("Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_find_location_menu():
    """Меню для поиска локации"""
    keyboard = [
        [InlineKeyboardButton("Выбрать район", callback_data="choose_district")],
        [InlineKeyboardButton("Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_district_menu():
    """Меню выбора района"""
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="find_location")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    
    # Инициализируем данные пользователя, если их еще нет
    if user_id not in user_data:
        user_data[user_id] = {
            'walking_location': None,
            'pet_photo_id': None,
            'friends': []
        }
    
    await update.message.reply_text(
        f'Привет, {user.first_name}! 👋\n\n'
        'Выберите действие из меню:',
        reply_markup=get_main_menu()
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Инициализируем данные пользователя, если их еще нет
    if user_id not in user_data:
        user_data[user_id] = {
            'walking_location': None,
            'pet_photo_id': None,
            'friends': []
        }
    
    callback_data = query.data
    
    if callback_data == "main_menu":
        await query.edit_message_text(
            "Главное меню:\n\nВыберите действие:",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    
    elif callback_data == "profile":
        walking_location = user_data[user_id].get('walking_location', 'не указано')
        pet_photo_status = "загружено" if user_data[user_id].get('pet_photo_id') else "не загружено"
        
        text = (
            "📋 Мой профиль\n\n"
            f"📍 Где я гуляю: {walking_location}\n"
            f"📷 Фото питомца: {pet_photo_status}\n\n"
            "Выберите действие:"
        )
        await query.edit_message_text(text, reply_markup=get_profile_menu())
        return ConversationHandler.END
    
    elif callback_data == "my_walking_location":
        await query.edit_message_text(
            "📍 Где я гуляю\n\n"
            "Напишите район или улицу, где вы гуляете:",
            reply_markup=get_walking_location_menu()
        )
        return WAITING_LOCATION
    
    elif callback_data == "pet_photo":
        await query.edit_message_text(
            "📷 Фото питомца\n\n"
            "Загрузите фото питомца из галереи или сделайте фото камерой:",
            reply_markup=get_profile_menu()
        )
        # Состояние для ожидания фото будет обработано в handle_photo
        return ConversationHandler.END
    
    elif callback_data == "walk_with_friends":
        await query.edit_message_text(
            "👥 Гулять с друзьями\n\n"
            "Выберите действие:",
            reply_markup=get_walk_with_friends_menu()
        )
        return ConversationHandler.END
    
    elif callback_data == "write_friend":
        # Получаем список друзей (в реальном проекте из БД)
        friends_list = user_data[user_id].get('friends', [])
        
        if not friends_list:
            text = (
                "✉️ Написать другу\n\n"
                "У вас пока нет друзей.\n"
                "Напишите имя пользователя или username друга (например: @username или Имя):"
            )
        else:
            text = "✉️ Написать другу\n\nВыберите друга из списка или напишите имя:\n\n"
            for i, friend in enumerate(friends_list, 1):
                text += f"{i}. {friend}\n"
            text += "\nИли напишите имя пользователя:"
        
        await query.edit_message_text(text, reply_markup=get_walk_with_friends_menu())
        return WAITING_FRIEND_NAME
    
    elif callback_data == "find_location":
        await query.edit_message_text(
            "🗺️ Найти локацию для прогулки\n\n"
            "Выберите действие:",
            reply_markup=get_find_location_menu()
        )
        return ConversationHandler.END
    
    elif callback_data == "choose_district":
        await query.edit_message_text(
            "🏘️ Выбрать район\n\n"
            "Напишите район, в котором нужно найти пользователей для прогулок:",
            reply_markup=get_district_menu()
        )
        return WAITING_DISTRICT
    
    elif callback_data == "find_vet":
        await query.edit_message_text(
            "🏥 Найти ветклинику\n\n"
            "Функция в разработке. Скоро здесь будет поиск ближайших ветклиник.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    
    elif callback_data == "find_pet_shop":
        await query.edit_message_text(
            "🛒 Найти зоомагазин\n\n"
            "Функция в разработке. Скоро здесь будет поиск ближайших зоомагазинов.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    
    return ConversationHandler.END


async def handle_location_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка текста для локации прогулок"""
    user_id = update.message.from_user.id
    location_text = update.message.text
    
    user_data[user_id]['walking_location'] = location_text
    
    # Показываем обновленный профиль
    walking_location = user_data[user_id].get('walking_location', 'не указано')
    pet_photo_status = "загружено" if user_data[user_id].get('pet_photo_id') else "не загружено"
    
    text = (
        f"✅ Локация сохранена: {location_text}\n\n"
        "📋 Мой профиль\n\n"
        f"📍 Где я гуляю: {walking_location}\n"
        f"📷 Фото питомца: {pet_photo_status}\n\n"
        "Выберите действие:"
    )
    await update.message.reply_text(text, reply_markup=get_profile_menu())
    
    return ConversationHandler.END


async def handle_friend_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка имени друга для отправки сообщения"""
    user_id = update.message.from_user.id
    friend_name = update.message.text
    
    # В реальном проекте здесь была бы отправка сообщения другу
    # Пока просто подтверждаем
    await update.message.reply_text(
        f"✅ Сообщение отправлено другу: {friend_name}\n\n"
        "В реальной версии здесь будет отправка сообщения.",
        reply_markup=get_walk_with_friends_menu()
    )
    
    return ConversationHandler.END


async def handle_district(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора района"""
    district = update.message.text
    
    # Пример локаций (в реальном проекте из БД или API)
    locations = [
        "Парк Горького",
        "Центральный сквер",
        "Лесопарк",
        "Набережная",
        "Спортивная площадка"
    ]
    
    text = f"🏘️ Район: {district}\n\n"
    text += "Выберите локацию из списка (напишите номер):\n\n"
    for i, loc in enumerate(locations, 1):
        text += f"{i}. {loc}\n"
    
    keyboard = [[InlineKeyboardButton("Назад", callback_data="choose_district")]]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Сохраняем район в контексте
    context.user_data['selected_district'] = district
    context.user_data['locations'] = locations
    
    return WAITING_LOCATION_CHOICE


async def handle_location_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора локации по номеру"""
    try:
        choice = int(update.message.text)
        locations = context.user_data.get('locations', [])
        district = context.user_data.get('selected_district', '')
        
        if 1 <= choice <= len(locations):
            selected_location = locations[choice - 1]
            await update.message.reply_text(
                f"✅ Выбрана локация: {selected_location}\n"
                f"📍 Район: {district}\n\n"
                "В реальной версии здесь будет поиск пользователей в этой локации.",
                reply_markup=get_find_location_menu()
            )
        else:
            await update.message.reply_text(
                "❌ Неверный номер. Выберите номер из списка:",
                reply_markup=get_district_menu()
            )
            return WAITING_LOCATION_CHOICE
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите номер локации:",
            reply_markup=get_district_menu()
        )
        return WAITING_LOCATION_CHOICE
    
    return ConversationHandler.END


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка загрузки фото питомца"""
    user_id = update.message.from_user.id
    
    # Инициализируем данные пользователя, если их еще нет
    if user_id not in user_data:
        user_data[user_id] = {
            'walking_location': None,
            'pet_photo_id': None,
            'friends': []
        }
    
    if update.message.photo:
        # Сохраняем file_id последнего (самого большого) фото
        photo = update.message.photo[-1]
        user_data[user_id]['pet_photo_id'] = photo.file_id
        
        # Показываем обновленный профиль
        walking_location = user_data[user_id].get('walking_location', 'не указано')
        pet_photo_status = "загружено"
        
        text = (
            "✅ Фото питомца успешно загружено!\n\n"
            "📋 Мой профиль\n\n"
            f"📍 Где я гуляю: {walking_location}\n"
            f"📷 Фото питомца: {pet_photo_status}\n\n"
            "Выберите действие:"
        )
        await update.message.reply_text(text, reply_markup=get_profile_menu())
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте фото.",
            reply_markup=get_profile_menu()
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений (когда не в состоянии ожидания)"""
    # Если пользователь не в состоянии ожидания, показываем главное меню
    await update.message.reply_text(
        "Выберите действие из меню:",
        reply_markup=get_main_menu()
    )


def main() -> None:
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler для обработки состояний
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback, pattern="^(my_walking_location|write_friend|choose_district)$")
        ],
        states={
            WAITING_LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_location_text),
                CallbackQueryHandler(button_callback, pattern="^profile$")
            ],
            WAITING_FRIEND_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_friend_name),
                CallbackQueryHandler(button_callback, pattern="^walk_with_friends$")
            ],
            WAITING_DISTRICT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_district),
                CallbackQueryHandler(button_callback, pattern="^find_location$")
            ],
            WAITING_LOCATION_CHOICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_location_choice),
                CallbackQueryHandler(button_callback, pattern="^choose_district$")
            ]
        },
        fallbacks=[CommandHandler("start", start), CallbackQueryHandler(button_callback)]
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

