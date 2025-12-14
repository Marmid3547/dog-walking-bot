import os
import json
import logging
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
WAITING_LOCATION, WAITING_FRIEND_NAME, WAITING_DISTRICT, WAITING_LOCATION_CHOICE, WAITING_SEARCH_USERNAME, WAITING_VERIFICATION_CODE = range(6)

# Хранение данных пользователей
user_data = {}
DATA_FILE = 'user_data.json'
# Хранение запросов на добавление в друзья (от кого -> кому)
friend_requests = {}  # {user_id: [list of user_ids who sent requests]}
# Хранение кодов верификации: {user_id: {'code': str, 'phone': str, 'timestamp': float}}
verification_codes = {}


def load_user_data():
    """Загружает данные пользователей из JSON файла"""
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Проверяем новый формат с friend_requests
                if isinstance(data, dict) and 'users' in data:
                    users = data['users']
                    user_data = {int(k): v for k, v in users.items()}
                    load_friend_requests()
                else:
                    # Старый формат - только user_data напрямую
                    user_data = {int(k): v for k, v in data.items()}
                    friend_requests = {}
                logger.info(f"Загружены данные для {len(user_data)} пользователей")
        else:
            user_data = {}
            friend_requests = {}
            logger.info("Файл данных не найден, создан новый словарь")
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных: {e}")
        user_data = {}
        friend_requests = {}


def save_user_data():
    """Сохраняет данные пользователей в JSON файл"""
    try:
        data_to_save = {
            'users': user_data,
            'friend_requests': friend_requests
        }
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        logger.debug("Данные пользователей сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")


def load_friend_requests():
    """Загружает запросы на добавление в друзья из сохраненных данных"""
    global friend_requests
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'friend_requests' in data:
                    requests = data['friend_requests']
                    friend_requests = {int(k): [int(i) for i in v] for k, v in requests.items()}
                else:
                    # Старый формат - только user_data
                    friend_requests = {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке запросов: {e}")
        friend_requests = {}


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
        [InlineKeyboardButton("📱 Поделиться контактом", callback_data="share_contact")],
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
        [InlineKeyboardButton("👥 Мои друзья", callback_data="my_friends")],
        [InlineKeyboardButton("Написать другу", callback_data="write_friend")],
        [InlineKeyboardButton("🔍 Найти пользователя", callback_data="search_user")],
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
    try:
        logger.info(f"Получена команда /start от пользователя {update.effective_user.id}")
        user = update.effective_user
        user_id = user.id
        
        # Инициализируем данные пользователя, если их еще нет
        if user_id not in user_data:
            user_data[user_id] = {
                'walking_location': None,
                'pet_photo_id': None,
                'friends': [],
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone_number': None,
                'phone_verified': False
            }
            save_user_data()  # Сохраняем нового пользователя
        else:
            # Обновляем данные пользователя при каждом старте
            user_data[user_id]['username'] = user.username
            user_data[user_id]['first_name'] = user.first_name
            user_data[user_id]['last_name'] = user.last_name
            save_user_data()  # Сохраняем обновления
        
        await update.message.reply_text(
            f'Привет, {user.first_name}! 👋\n\n'
            'Выберите действие из меню:',
            reply_markup=get_main_menu()
        )
        logger.info(f"Ответ отправлен пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка в обработчике start: {e}", exc_info=True)


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
        phone_number = user_data[user_id].get('phone_number', 'не указан')
        phone_verified = user_data[user_id].get('phone_verified', False)
        phone_status = "✅ подтвержден" if phone_verified else "❌ не подтвержден" if phone_number != 'не указан' else "не указан"
        
        text = (
            "📋 Мой профиль\n\n"
            f"📍 Где я гуляю: {walking_location}\n"
            f"📷 Фото питомца: {pet_photo_status}\n"
            f"📱 Телефон: {phone_number} ({phone_status})\n\n"
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
    
    elif callback_data == "share_contact":
        # Проверяем, есть ли уже номер телефона
        phone_number = user_data[user_id].get('phone_number')
        phone_verified = user_data[user_id].get('phone_verified', False)
        
        if phone_number and phone_verified:
            await query.edit_message_text(
                f"📱 Контакт уже подтвержден\n\n"
                f"Ваш номер телефона: {phone_number}\n"
                f"Статус: ✅ Подтвержден\n\n"
                "Если хотите изменить номер, нажмите кнопку еще раз.",
                reply_markup=get_profile_menu()
            )
            return ConversationHandler.END
        
        # Создаем клавиатуру с кнопкой для отправки контакта
        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await query.edit_message_text(
            "📱 Поделиться контактом\n\n"
            "Для авторизации и использования реферальной системы нам нужен ваш номер телефона.\n\n"
            "Нажмите кнопку ниже, чтобы поделиться контактом:"
        )
        
        # Отправляем сообщение с кнопкой для отправки контакта
        await context.bot.send_message(
            chat_id=user_id,
            text="👇 Нажмите кнопку, чтобы поделиться номером телефона:",
            reply_markup=contact_keyboard
        )
        
        return ConversationHandler.END
    
    elif callback_data == "walk_with_friends":
        await query.edit_message_text(
            "👥 Гулять с друзьями\n\n"
            "Выберите действие:",
            reply_markup=get_walk_with_friends_menu()
        )
        return ConversationHandler.END
    
    elif callback_data == "my_friends":
        # Получаем список друзей пользователя
        friends_list = user_data[user_id].get('friends', [])
        
        if not friends_list:
            await query.edit_message_text(
                "👥 Мои друзья\n\n"
                "У вас пока нет друзей.\n\n"
                "Используйте кнопку '🔍 Найти пользователя' чтобы найти и добавить друзей.",
                reply_markup=get_walk_with_friends_menu()
            )
        else:
            text = f"👥 Мои друзья ({len(friends_list)})\n\n"
            keyboard = []
            
            for i, friend in enumerate(friends_list, 1):
                if isinstance(friend, dict):
                    friend_id = friend.get('user_id')
                    friend_name = friend.get('name', 'Друг')
                    
                    # Получаем актуальную информацию о друге
                    friend_info = user_data.get(friend_id, {})
                    walking_location = friend_info.get('walking_location', 'не указано')
                    
                    text += f"{i}. {friend_name}\n"
                    if walking_location != 'не указано':
                        text += f"   📍 {walking_location}\n"
                    text += "\n"
                    
                    # Кнопка для просмотра профиля друга
                    keyboard.append([InlineKeyboardButton(
                        f"👤 {friend_name}",
                        callback_data=f"view_friend_{friend_id}"
                    )])
                else:
                    text += f"{i}. {friend}\n\n"
                    keyboard.append([InlineKeyboardButton(
                        f"{i}. {friend}",
                        callback_data=f"view_friend_old_{i}"
                    )])
            
            keyboard.append([InlineKeyboardButton("Назад", callback_data="walk_with_friends")])
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("view_friend_"):
        # Просмотр профиля друга
        friend_id_str = callback_data.split("_")[2]
        
        # Обработка старых записей без user_id
        if friend_id_str.startswith("old_"):
            await query.edit_message_text(
                "ℹ️ Это старый формат записи друга. Пожалуйста, добавьте друга заново через поиск.",
                reply_markup=get_walk_with_friends_menu()
            )
            return ConversationHandler.END
        
        friend_id = int(friend_id_str)
        friend_info = user_data.get(friend_id)
        
        if friend_info:
            display_name = friend_info.get('first_name', 'Пользователь')
            if friend_info.get('last_name'):
                display_name += f" {friend_info['last_name']}"
            username = friend_info.get('username', 'не указан')
            walking_location = friend_info.get('walking_location', 'не указано')
            pet_photo_status = "есть" if friend_info.get('pet_photo_id') else "нет"
            
            text = (
                f"👤 Профиль друга\n\n"
                f"Имя: {display_name}\n"
                f"Username: @{username}\n"
                f"📍 Где гуляет: {walking_location}\n"
                f"📷 Фото питомца: {pet_photo_status}\n\n"
                "Выберите действие:"
            )
            
            keyboard = [
                [InlineKeyboardButton("✉️ Написать сообщение", callback_data=f"write_to_{friend_id}")],
                [InlineKeyboardButton("🗑️ Удалить из друзей", callback_data=f"remove_friend_{friend_id}")],
                [InlineKeyboardButton("Назад", callback_data="my_friends")]
            ]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "❌ Пользователь не найден. Возможно, он удалил свой аккаунт.",
                reply_markup=get_walk_with_friends_menu()
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("remove_friend_"):
        # Удаление друга из списка
        friend_id = int(callback_data.split("_")[2])
        friends_list = user_data[user_id].get('friends', [])
        
        # Удаляем друга из списка
        updated_friends = [
            f for f in friends_list 
            if isinstance(f, dict) and f.get('user_id') != friend_id
        ]
        
        user_data[user_id]['friends'] = updated_friends
        save_user_data()  # Сохраняем изменения
        
        friend_info = user_data.get(friend_id, {})
        friend_name = friend_info.get('first_name', 'Пользователь') if friend_info else 'Пользователь'
        
        await query.edit_message_text(
            f"✅ {friend_name} удален из списка друзей.",
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
            await query.edit_message_text(text, reply_markup=get_walk_with_friends_menu())
        else:
            text = "✉️ Написать другу\n\nВыберите друга из списка или напишите имя:\n\n"
            keyboard = []
            for i, friend in enumerate(friends_list, 1):
                if isinstance(friend, dict):
                    friend_name = friend.get('name', 'Друг')
                    friend_id = friend.get('user_id')
                    text += f"{i}. {friend_name}\n"
                    keyboard.append([InlineKeyboardButton(
                        f"{i}. {friend_name}",
                        callback_data=f"write_to_{friend_id}"
                    )])
                else:
                    text += f"{i}. {friend}\n"
            text += "\nИли напишите имя пользователя:"
            
            keyboard.append([InlineKeyboardButton("Назад", callback_data="walk_with_friends")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        return WAITING_FRIEND_NAME
    
    elif callback_data == "search_user":
        await query.edit_message_text(
            "🔍 Найти пользователя\n\n"
            "Введите для поиска:\n"
            "• Username (с @ или без): @username или username\n"
            "• Имя или фамилию пользователя\n"
            "• Номер телефона (только цифры, с + или без): +79991234567 или 79991234567\n\n"
            "Примеры:\n"
            "• @ivan_petrov\n"
            "• Иван\n"
            "• +79991234567",
            reply_markup=get_walk_with_friends_menu()
        )
        return WAITING_SEARCH_USERNAME
    
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
    
    elif callback_data.startswith("select_user_"):
        # Обработка выбора пользователя из результатов поиска
        selected_user_id = int(callback_data.split("_")[2])
        selected_user = user_data.get(selected_user_id)
        
        if selected_user:
            display_name = selected_user.get('first_name', 'Пользователь')
            if selected_user.get('last_name'):
                display_name += f" {selected_user['last_name']}"
            username = selected_user.get('username', 'не указан')
            walking_location = selected_user.get('walking_location', 'не указано')
            phone_number = selected_user.get('phone_number', 'не указан')
            phone_verified = selected_user.get('phone_verified', False)
            phone_status = "✅ подтвержден" if phone_verified else "❌ не подтвержден" if phone_number != 'не указан' else "не указан"
            
            # Показываем номер телефона только если он подтвержден (для приватности)
            phone_display = "не указан"
            if phone_number and phone_number != 'не указан':
                if phone_verified:
                    # Показываем только последние 4 цифры для приватности
                    phone_digits = ''.join(filter(str.isdigit, phone_number))
                    if len(phone_digits) >= 4:
                        phone_display = f"+***{phone_digits[-4:]} ({phone_status})"
                    else:
                        phone_display = f"+{phone_number} ({phone_status})"
                else:
                    phone_display = "не подтвержден"
            
            text = (
                f"👤 Профиль пользователя\n\n"
                f"Имя: {display_name}\n"
                f"Username: @{username}\n"
                f"📱 Телефон: {phone_display}\n"
                f"📍 Где гуляет: {walking_location}\n\n"
                "Выберите действие:"
            )
            
            # Проверяем, является ли пользователь уже другом
            friends_list = user_data.get(user_id, {}).get('friends', [])
            is_friend = any(
                isinstance(f, dict) and f.get('user_id') == selected_user_id 
                for f in friends_list
            )
            
            # Проверяем, есть ли уже запрос
            has_request = selected_user_id in friend_requests.get(user_id, [])
            
            keyboard = [
                [InlineKeyboardButton("✉️ Написать сообщение", callback_data=f"write_to_{selected_user_id}")]
            ]
            
            if is_friend:
                keyboard.append([InlineKeyboardButton("✅ Уже в друзьях", callback_data=f"already_friend_{selected_user_id}")])
            elif has_request:
                keyboard.append([InlineKeyboardButton("⏳ Запрос отправлен", callback_data=f"request_sent_{selected_user_id}")])
            else:
                keyboard.append([InlineKeyboardButton("➕ Добавить в друзья", callback_data=f"add_friend_{selected_user_id}")])
            
            keyboard.append([InlineKeyboardButton("Назад", callback_data="walk_with_friends")])
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "❌ Пользователь не найден.",
                reply_markup=get_walk_with_friends_menu()
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("write_to_"):
        # Отправка сообщения пользователю
        target_user_id = int(callback_data.split("_")[2])
        target_user = user_data.get(target_user_id)
        
        if target_user:
            display_name = target_user.get('first_name', 'Пользователь')
            await query.edit_message_text(
                f"✉️ Написать сообщение\n\n"
                f"Вы хотите написать пользователю: {display_name}\n\n"
                "В реальной версии здесь будет форма для отправки сообщения.",
                reply_markup=get_walk_with_friends_menu()
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("add_friend_"):
        # Добавление пользователя в друзья
        target_user_id = int(callback_data.split("_")[2])
        target_user = user_data.get(target_user_id)
        
        if target_user:
            if user_id not in user_data:
                user_data[user_id] = {
                    'walking_location': None,
                    'pet_photo_id': None,
                    'friends': [],
                    'username': None,
                    'first_name': None,
                    'last_name': None
                }
            
            friends_list = user_data[user_id].get('friends', [])
            friend_name = target_user.get('first_name', 'Пользователь')
            if target_user.get('username'):
                friend_name += f" (@{target_user['username']})"
            
            # Проверяем, не является ли уже другом
            is_already_friend = any(
                isinstance(f, dict) and f.get('user_id') == target_user_id 
                for f in friends_list
            )
            
            if is_already_friend:
                await query.edit_message_text(
                    f"ℹ️ Пользователь {friend_name} уже в вашем списке друзей.",
                    reply_markup=get_walk_with_friends_menu()
                )
            else:
                # Добавляем в друзья
                friends_list.append({
                    'user_id': target_user_id,
                    'name': friend_name,
                    'added_at': None  # Можно добавить timestamp
                })
                user_data[user_id]['friends'] = friends_list
                
                # Взаимное добавление: добавляем текущего пользователя в друзья к найденному пользователю
                if target_user_id not in user_data:
                    user_data[target_user_id] = {
                        'walking_location': None,
                        'pet_photo_id': None,
                        'friends': [],
                        'username': target_user.get('username'),
                        'first_name': target_user.get('first_name'),
                        'last_name': target_user.get('last_name')
                    }
                
                target_friends = user_data[target_user_id].get('friends', [])
                current_user_name = query.from_user.first_name or 'Пользователь'
                if query.from_user.username:
                    current_user_name += f" (@{query.from_user.username})"
                
                # Проверяем, не добавлен ли уже текущий пользователь
                is_current_user_friend = any(
                    isinstance(f, dict) and f.get('user_id') == user_id 
                    for f in target_friends
                )
                
                if not is_current_user_friend:
                    target_friends.append({
                        'user_id': user_id,
                        'name': current_user_name
                    })
                    user_data[target_user_id]['friends'] = target_friends
                
                save_user_data()  # Сохраняем изменения
                
                # Пытаемся отправить уведомление другому пользователю (если он онлайн)
                try:
                    target_user_info = user_data.get(target_user_id, {})
                    if target_user_info:
                        notification_text = (
                            f"👋 Новый друг!\n\n"
                            f"{current_user_name} добавил(а) вас в друзья.\n\n"
                            f"Используйте меню '👥 Гулять с друзьями' → '👥 Мои друзья' чтобы увидеть список."
                        )
                        # В реальном проекте здесь была бы отправка сообщения через bot.send_message
                        # await context.bot.send_message(chat_id=target_user_id, text=notification_text)
                        logger.info(f"Пользователь {user_id} добавил {target_user_id} в друзья")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления: {e}")
                
                await query.edit_message_text(
                    f"✅ Пользователь {friend_name} добавлен в друзья!\n\n"
                    f"Теперь вы можете найти его в разделе '👥 Мои друзья'.",
                    reply_markup=get_walk_with_friends_menu()
                )
        return ConversationHandler.END
    
    elif callback_data.startswith("already_friend_"):
        # Пользователь уже в друзьях
        await query.answer("Этот пользователь уже в вашем списке друзей", show_alert=True)
        return ConversationHandler.END
    
    elif callback_data.startswith("request_sent_"):
        # Запрос уже отправлен
        await query.answer("Запрос на добавление в друзья уже отправлен", show_alert=True)
        return ConversationHandler.END
    
    return ConversationHandler.END


async def handle_location_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка текста для локации прогулок"""
    user_id = update.message.from_user.id
    location_text = update.message.text
    
    user_data[user_id]['walking_location'] = location_text
    save_user_data()  # Сохраняем изменения
    
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


async def handle_search_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка поиска пользователя по username, имени или номеру телефона"""
    user_id = update.message.from_user.id
    search_query = update.message.text.strip()
    
    # Определяем тип поиска: телефон или текст
    # Убираем все нецифровые символы для проверки на телефон
    phone_digits = ''.join(filter(str.isdigit, search_query))
    is_phone_search = len(phone_digits) >= 7  # Минимум 7 цифр для номера телефона
    
    # Убираем @ если есть (для username)
    if search_query.startswith('@'):
        search_query = search_query[1:]
    
    # Нормализуем номер телефона для поиска (убираем + и пробелы)
    normalized_search_phone = None
    if is_phone_search:
        # Убираем + в начале если есть
        normalized_search_phone = phone_digits
        if normalized_search_phone.startswith('7') and len(normalized_search_phone) == 11:
            # Российский номер, оставляем как есть
            pass
        elif normalized_search_phone.startswith('8') and len(normalized_search_phone) == 11:
            # Заменяем 8 на 7 для российских номеров
            normalized_search_phone = '7' + normalized_search_phone[1:]
    
    search_lower = search_query.lower()
    
    # Поиск пользователей
    found_users = []
    for uid, user_info in user_data.items():
        # Не показываем самого пользователя в результатах
        if uid == user_id:
            continue
        
        match_found = False
        
        # Поиск по номеру телефона
        if is_phone_search and normalized_search_phone:
            user_phone = user_info.get('phone_number', '')
            if user_phone:
                # Нормализуем номер пользователя
                user_phone_digits = ''.join(filter(str.isdigit, user_phone))
                if user_phone_digits:
                    # Проверяем совпадение (полное или частичное)
                    if normalized_search_phone in user_phone_digits or user_phone_digits in normalized_search_phone:
                        match_found = True
                        # Показываем только последние 4 цифры для приватности
                        phone_display = f"***{user_phone_digits[-4:]}" if len(user_phone_digits) >= 4 else "***"
        
        # Поиск по username
        if not match_found:
            username = user_info.get('username', '').lower() if user_info.get('username') else ''
            if username and search_lower in username:
                match_found = True
        
        # Поиск по имени
        if not match_found:
            first_name = user_info.get('first_name', '').lower() if user_info.get('first_name') else ''
            if first_name and search_lower in first_name:
                match_found = True
        
        # Поиск по фамилии
        if not match_found:
            last_name = user_info.get('last_name', '').lower() if user_info.get('last_name') else ''
            if last_name and search_lower in last_name:
                match_found = True
        
        # Поиск по полному имени (имя + фамилия)
        if not match_found:
            full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip().lower()
            if full_name and search_lower in full_name:
                match_found = True
        
        if match_found:
            found_users.append({
                'user_id': uid,
                'username': user_info.get('username'),
                'first_name': user_info.get('first_name'),
                'last_name': user_info.get('last_name'),
                'phone_number': user_info.get('phone_number'),
                'phone_verified': user_info.get('phone_verified', False)
            })
    
    if not found_users:
        search_type = "номеру телефона" if is_phone_search else "запросу"
        await update.message.reply_text(
            f"❌ Пользователь по {search_type} '{search_query}' не найден.\n\n"
            "Попробуйте:\n"
            "• Другой username (@username)\n"
            "• Имя или фамилию\n"
            "• Номер телефона\n\n"
            "Убедитесь, что пользователь зарегистрирован в боте и поделился контактом.",
            reply_markup=get_walk_with_friends_menu()
        )
    else:
        # Показываем результаты поиска
        text = f"🔍 Найдено пользователей: {len(found_users)}\n\n"
        
        # Создаем клавиатуру с кнопками для выбора пользователя
        keyboard = []
        for i, user in enumerate(found_users[:10], 1):  # Ограничиваем 10 результатами
            display_name = user['first_name'] or 'Пользователь'
            if user['last_name']:
                display_name += f" {user['last_name']}"
            if user['username']:
                display_name += f" (@{user['username']})"
            
            # Добавляем индикатор подтвержденного телефона
            if user.get('phone_verified'):
                display_name += " ✓"
            
            keyboard.append([InlineKeyboardButton(
                f"{i}. {display_name}",
                callback_data=f"select_user_{user['user_id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("Назад", callback_data="walk_with_friends")])
        
        text += "Выберите пользователя:"
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
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


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка получения контакта от пользователя"""
    user_id = update.message.from_user.id
    contact = update.message.contact
    
    if contact:
        phone_number = contact.phone_number
        # Убираем + если есть
        if phone_number.startswith('+'):
            phone_number = phone_number[1:]
        
        # Инициализируем данные пользователя, если их еще нет
        if user_id not in user_data:
            user_data[user_id] = {
                'walking_location': None,
                'pet_photo_id': None,
                'friends': [],
                'phone_number': None,
                'phone_verified': False
            }
        
        # Сохраняем номер телефона
        user_data[user_id]['phone_number'] = phone_number
        
        # Ищем совпадения в базе данных (проверяем других пользователей с таким же номером)
        matching_users = []
        for uid, user_info in user_data.items():
            if uid != user_id and user_info.get('phone_number') == phone_number:
                matching_users.append({
                    'user_id': uid,
                    'name': user_info.get('first_name', 'Пользователь'),
                    'username': user_info.get('username')
                })
        
        # Генерируем код верификации
        verification_code = str(random.randint(1000, 9999))
        verification_codes[user_id] = {
            'code': verification_code,
            'phone': phone_number,
            'timestamp': time.time()
        }
        
        # Удаляем клавиатуру с кнопкой
        await update.message.reply_text(
            f"✅ Контакт получен!\n\n"
            f"📱 Ваш номер: +{phone_number}\n\n"
            f"🔐 Код подтверждения: {verification_code}\n\n"
            f"Введите этот код для подтверждения номера телефона:",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Если найдены совпадения, сообщаем об этом
        if matching_users:
            matches_text = "Найдены пользователи с таким же номером:\n"
            for match in matching_users:
                matches_text += f"• {match['name']}"
                if match['username']:
                    matches_text += f" (@{match['username']})"
                matches_text += "\n"
            
            await context.bot.send_message(
                chat_id=user_id,
                text=matches_text
            )
        
        # Сохраняем данные
        save_user_data()
        
        # Переводим в состояние ожидания кода верификации через ConversationHandler
        # Это будет обработано в handle_text_message
        context.user_data['waiting_verification'] = True
    else:
        await update.message.reply_text(
            "❌ Не удалось получить контакт. Попробуйте еще раз.",
            reply_markup=ReplyKeyboardRemove()
        )


async def handle_verification_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кода верификации"""
    user_id = update.message.from_user.id
    entered_code = update.message.text.strip()
    
    # Проверяем код верификации
    if user_id in verification_codes:
        stored_code = verification_codes[user_id]['code']
        timestamp = verification_codes[user_id]['timestamp']
        
        # Проверяем, не истек ли код (5 минут)
        if time.time() - timestamp > 300:
            await update.message.reply_text(
                "❌ Код подтверждения истек. Пожалуйста, поделитесь контактом заново.",
                reply_markup=get_profile_menu()
            )
            del verification_codes[user_id]
            return ConversationHandler.END
        
        if entered_code == stored_code:
            # Код верный - подтверждаем номер
            user_data[user_id]['phone_verified'] = True
            phone_number = verification_codes[user_id]['phone']
            save_user_data()
            
            # Удаляем код из временного хранилища
            del verification_codes[user_id]
            context.user_data.pop('waiting_verification', None)
            
            await update.message.reply_text(
                f"✅ Номер телефона подтвержден!\n\n"
                f"📱 Ваш номер: +{phone_number}\n\n"
                f"Теперь вы можете использовать все функции бота, включая реферальную систему.",
                reply_markup=get_profile_menu()
            )
            
            # Показываем обновленный профиль
            walking_location = user_data[user_id].get('walking_location', 'не указано')
            pet_photo_status = "загружено" if user_data[user_id].get('pet_photo_id') else "не загружено"
            
            text = (
                "📋 Мой профиль\n\n"
                f"📍 Где я гуляю: {walking_location}\n"
                f"📷 Фото питомца: {pet_photo_status}\n"
                f"📱 Телефон: +{phone_number} (✅ подтвержден)\n\n"
                "Выберите действие:"
            )
            await update.message.reply_text(text, reply_markup=get_profile_menu())
        else:
            await update.message.reply_text(
                "❌ Неверный код подтверждения. Попробуйте еще раз:"
            )
            return WAITING_VERIFICATION_CODE
    else:
        await update.message.reply_text(
            "❌ Код подтверждения не найден. Пожалуйста, поделитесь контактом заново.",
            reply_markup=get_profile_menu()
        )
    
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
        save_user_data()  # Сохраняем изменения
        
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
    user_id = update.message.from_user.id
    
    # Проверяем, ожидается ли код верификации
    if context.user_data.get('waiting_verification'):
        await handle_verification_code(update, context)
        return
    
    # Если пользователь не в состоянии ожидания, показываем главное меню
    await update.message.reply_text(
        "Выберите действие из меню:",
        reply_markup=get_main_menu()
    )


def main() -> None:
    """Запуск бота"""
    try:
        logger.info(f"Запуск бота с токеном: {BOT_TOKEN[:10]}..." if BOT_TOKEN else "Токен не найден!")
        
        # Загружаем данные пользователей из файла
        load_user_data()
        
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # ConversationHandler для обработки состояний
        conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(button_callback, pattern="^(my_walking_location|write_friend|choose_district|search_user|share_contact)$")
            ],
            per_message=False,
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
                ],
                WAITING_SEARCH_USERNAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_username),
                    CallbackQueryHandler(button_callback, pattern="^walk_with_friends$")
                ],
                WAITING_VERIFICATION_CODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_verification_code),
                    CallbackQueryHandler(button_callback, pattern="^profile$")
                ]
            },
            fallbacks=[CommandHandler("start", start), CallbackQueryHandler(button_callback)]
        )
        
        # Регистрируем обработчики (ВАЖНО: порядок имеет значение!)
        # Сначала регистрируем команду /start, чтобы она обрабатывалась до ConversationHandler
        application.add_handler(CommandHandler("start", start))
        logger.info("Обработчик команды /start зарегистрирован")
        
        application.add_handler(conv_handler)
        logger.info("ConversationHandler зарегистрирован")
        
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # Запускаем бота
        logger.info("Бот запущен и готов к работе...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True  # Игнорировать старые обновления при запуске
        )
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
