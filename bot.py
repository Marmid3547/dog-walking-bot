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
from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]

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
ADMIN_ID = os.getenv('ADMIN_ID')  # ID администратора для управления подписчиками

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Убедитесь, что вы создали .env файл с токеном.")

# Состояния для ConversationHandler
WAITING_LOCATION, WAITING_FRIEND_NAME, WAITING_DISTRICT, WAITING_LOCATION_CHOICE, WAITING_SEARCH_USERNAME, WAITING_VERIFICATION_CODE, WAITING_ADMIN_TAG, WAITING_MESSAGE_TEXT, WAITING_ADMIN_MESSAGE_TEXT = range(9)

# Хранение данных пользователей
user_data = {}
DATA_FILE = 'user_data.json'
# Хранение запросов на добавление в друзья (от кого -> кому)
friend_requests = {}  # {user_id: [list of user_ids who sent requests]}
# Хранение кодов верификации: {user_id: {'code': str, 'phone': str, 'timestamp': float}}
verification_codes = {}


def load_user_data():
    """Загружает данные пользователей из JSON файла"""
    global user_data, friend_requests
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


def get_main_menu(user_id=None):
    """Создает главное меню с 5 кнопками"""
    keyboard = [
        [InlineKeyboardButton("Мой профиль", callback_data="profile")],
        [InlineKeyboardButton("Гулять с друзьями", callback_data="walk_with_friends")],
        [InlineKeyboardButton("Найти локацию для прогулки", callback_data="find_location")],
        [InlineKeyboardButton("Найти ветклинику", callback_data="find_vet")],
        [InlineKeyboardButton("Найти зоомагазин", callback_data="find_pet_shop")]
    ]
    # Добавляем кнопку администратора, если пользователь - администратор
    if ADMIN_ID and user_id and str(user_id) == str(ADMIN_ID):
        keyboard.append([InlineKeyboardButton("👥 Управление подписчиками", callback_data="admin_subscribers")])
    return InlineKeyboardMarkup(keyboard)


def get_profile_menu():
    """Создает меню профиля"""
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="main_menu")],
        [InlineKeyboardButton("Где я гуляю", callback_data="my_walking_location")],
        [InlineKeyboardButton("Фото питомца", callback_data="pet_photo")],
        [InlineKeyboardButton("📱 Поделиться контактом", callback_data="share_contact")]
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
        [InlineKeyboardButton("Назад", callback_data="main_menu")],
        [InlineKeyboardButton("👥 Мои друзья", callback_data="my_friends")],
        [InlineKeyboardButton("📥 Входящие запросы", callback_data="friend_requests_incoming")],
        [InlineKeyboardButton("Написать другу", callback_data="write_friend")],
        [InlineKeyboardButton("🔍 Найти пользователя", callback_data="search_user")],
        [InlineKeyboardButton("🐕 Позвать гулять", callback_data="invite_to_walk")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_find_location_menu():
    """Меню для поиска локации"""
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="main_menu")],
        [InlineKeyboardButton("🗺️ Выбрать регион", callback_data="choose_region")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_regions_list():
    """Список регионов России"""
    regions = [
        "Москва", "Санкт-Петербург", "Московская область", "Ленинградская область",
        "Краснодарский край", "Ростовская область", "Республика Татарстан",
        "Свердловская область", "Челябинская область", "Республика Башкортостан",
        "Нижегородская область", "Самарская область", "Новосибирская область",
        "Красноярский край", "Воронежская область", "Пермский край",
        "Волгоградская область", "Омская область", "Республика Дагестан",
        "Тюменская область", "Иркутская область", "Кемеровская область",
        "Саратовская область", "Тульская область", "Ульяновская область",
        "Ярославская область", "Алтайский край", "Республика Крым",
        "Хабаровский край", "Ставропольский край", "Белгородская область",
        "Архангельская область", "Калужская область", "Тверская область",
        "Липецкая область", "Оренбургская область", "Курская область",
        "Республика Саха (Якутия)", "Приморский край", "Тамбовская область"
    ]
    return regions


def get_regions_menu():
    """Меню выбора региона"""
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="find_location")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_districts_by_region(region):
    """Получает список районов по региону"""
    # Базовый список районов для популярных регионов
    districts_map = {
        "Москва": [
            "Центральный", "Северный", "Северо-Восточный", "Восточный",
            "Юго-Восточный", "Южный", "Юго-Западный", "Западный",
            "Северо-Западный", "Зеленоградский", "Новомосковский", "Троицкий"
        ],
        "Санкт-Петербург": [
            "Адмиралтейский", "Василеостровский", "Выборгский", "Калининский",
            "Кировский", "Колпинский", "Красногвардейский", "Красносельский",
            "Кронштадтский", "Курортный", "Московский", "Невский",
            "Петроградский", "Петродворцовый", "Приморский", "Пушкинский",
            "Фрунзенский", "Центральный"
        ],
        "Московская область": [
            "Балашиха", "Подольск", "Химки", "Королёв", "Мытищи",
            "Люберцы", "Коломна", "Электросталь", "Одинцово", "Красногорск"
        ],
        "Краснодарский край": [
            "Краснодар", "Сочи", "Новороссийск", "Армавир", "Ейск",
            "Кропоткин", "Анапа", "Геленджик", "Туапсе", "Славянск-на-Кубани"
        ],
        "Ленинградская область": [
            "Всеволожск", "Гатчина", "Выборг", "Сосновый Бор", "Тихвин",
            "Кириши", "Кингисепп", "Волхов", "Сланцы", "Луга"
        ]
    }
    
    # Возвращаем районы для региона или общий список
    if region in districts_map:
        return districts_map[region]
    else:
        # Для регионов без данных возвращаем типовой список районов
        return [
            "Центральный район", "Северный район", "Южный район",
            "Восточный район", "Западный район"
        ]


def get_walking_places_by_district(region, district):
    """Получает список мест для прогулок по району"""
    # Специфичные места для известных регионов и районов
    # В реальном приложении это можно хранить в базе данных
    places_map = {
        ("Москва", "Центральный"): [
            "Парк Горького", "Сокольники", "Красная площадь", "Александровский сад",
            "Нескучный сад", "Царицыно", "Коломенское", "Измайловский парк"
        ],
        ("Москва", "Северный"): [
            "Парк Дружбы", "Парк Северного речного вокзала", "Лихоборские пруды",
            "Алтуфьевский парк", "Лианозовский парк"
        ],
        ("Москва", "Южный"): [
            "Царицыно", "Битцевский лесопарк", "Коломенское", "Царицынские пруды",
            "Парк усадьбы Люблино"
        ],
        ("Санкт-Петербург", "Центральный"): [
            "Летний сад", "Марсово поле", "Михайловский сад", "Парк 300-летия",
            "Елагин остров", "Таврический сад", "Александровский парк"
        ],
        ("Санкт-Петербург", "Приморский"): [
            "Парк 300-летия Санкт-Петербурга", "Приморский парк Победы",
            "Елагин остров", "Крестовский остров"
        ],
    }
    
    # Проверяем, есть ли специфичные места для этого района
    key = (region, district)
    if key in places_map:
        return places_map[key]
    
    # Если нет специфичных мест, формируем общий список с названием района
    base_places = [
        f"Центральный парк {district}",
        f"Парк Победы {district}",
        f"Лесопарк {district}",
        f"Сквер у озера {district}",
        f"Набережная {district}",
        f"Парк культуры и отдыха {district}",
        f"Детский парк {district}",
        f"Ботанический сад {district}",
        f"Лесная зона {district}",
        f"Сквер возле реки {district}",
        f"Парк развлечений {district}",
        f"Аллея для прогулок {district}",
        f"Зона отдыха {district}",
        f"Парк с озером {district}",
        f"Природный парк {district}"
    ]
    
    return base_places


def get_place_info(region, district, place):
    """Получает информацию о месте (координаты для Яндекс карт и фото)"""
    import urllib.parse
    
    # Примерные координаты для известных мест
    # В реальном приложении это должно храниться в базе данных
    places_coords = {
        "Парк Горького": {"lat": "55.7326", "lon": "37.6017"},
        "Сокольники": {"lat": "55.7902", "lon": "37.6769"},
        "Летний сад": {"lat": "59.9444", "lon": "30.3372"},
        "Марсово поле": {"lat": "59.9439", "lon": "30.3323"},
        "Красная площадь": {"lat": "55.7539", "lon": "37.6208"},
        "Александровский сад": {"lat": "55.7520", "lon": "37.6156"},
        "Нескучный сад": {"lat": "55.7147", "lon": "37.5964"},
        "Царицыно": {"lat": "55.6214", "lon": "37.6811"},
        "Коломенское": {"lat": "55.6682", "lon": "37.6685"},
        "Измайловский парк": {"lat": "55.7892", "lon": "37.7735"},
    }
    
    # Если есть координаты для места - используем их
    if place in places_coords:
        coords = places_coords[place]
        yandex_map_url = f"https://yandex.ru/maps/?pt={coords['lon']},{coords['lat']}&z=15"
    else:
        # Генерируем URL для поиска места на Яндекс картах с правильным URL-кодированием
        search_query = f"{place}, {district}, {region}"
        encoded_query = urllib.parse.quote(search_query)
        yandex_map_url = f"https://yandex.ru/maps/?text={encoded_query}"
    
    # URL для фото (можно использовать placeholder или реальные фото)
    # Для демонстрации используем placeholder изображение
    photo_url = None  # Можно добавить реальные URL фото мест
    
    return {
        "yandex_map_url": yandex_map_url,
        "photo_url": photo_url
    }


def get_district_menu():
    """Меню выбора района"""
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="find_location")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_menu():
    """Меню администратора"""
    keyboard = [
        [InlineKeyboardButton("👥 Список подписчиков", callback_data="admin_list_subscribers")],
        [InlineKeyboardButton("Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_subscriber_management_menu(subscriber_id):
    """Меню управления конкретным подписчиком"""
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="admin_list_subscribers")],
        [InlineKeyboardButton("🏷️ Добавить метку", callback_data=f"admin_add_tag_{subscriber_id}")],
        [InlineKeyboardButton("🏷️ Удалить метку", callback_data=f"admin_remove_tag_{subscriber_id}")],
        [InlineKeyboardButton("✉️ Написать сообщение", callback_data=f"admin_message_{subscriber_id}")],
        [InlineKeyboardButton("🗑️ Удалить контакт", callback_data=f"admin_delete_{subscriber_id}")]
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
                'phone_verified': False,
                'tags': [],
                'age': None
            }
            save_user_data()  # Сохраняем нового пользователя
        else:
            # Обновляем данные пользователя при каждом старте
            if 'username' not in user_data[user_id]:
                user_data[user_id]['username'] = None
            if 'first_name' not in user_data[user_id]:
                user_data[user_id]['first_name'] = None
            if 'last_name' not in user_data[user_id]:
                user_data[user_id]['last_name'] = None
            if 'tags' not in user_data[user_id]:
                user_data[user_id]['tags'] = []
            if 'age' not in user_data[user_id]:
                user_data[user_id]['age'] = None
            
            user_data[user_id]['username'] = user.username
            user_data[user_id]['first_name'] = user.first_name
            user_data[user_id]['last_name'] = user.last_name
            save_user_data()  # Сохраняем обновления
        
        user_name = user.first_name or 'Друг'
        await update.message.reply_text(
            f'Привет, {user_name}! 👋\n\n'
            'Выберите действие из меню:',
            reply_markup=get_main_menu(user_id)
        )
        logger.info(f"Ответ отправлен пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка в обработчике start: {e}", exc_info=True)
        # Даже при ошибке пытаемся отправить сообщение пользователю
        try:
            await update.message.reply_text(
                'Привет! 👋\n\n'
                'Выберите действие из меню:',
                reply_markup=get_main_menu(None)
            )
        except Exception as e2:
            logger.error(f"Критическая ошибка при отправке ответа: {e2}", exc_info=True)


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
            'friends': [],
            'tags': [],
            'age': None
        }
    
    callback_data = query.data
    
    if callback_data == "main_menu":
        await query.edit_message_text(
            "Главное меню:\n\nВыберите действие:",
            reply_markup=get_main_menu(user_id)
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
        
        # Создаем inline-кнопку "Назад"
        back_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data="profile")]
        ])
        
        await query.edit_message_text(
            "📱 Поделиться контактом\n\n"
            "Для авторизации и использования реферальной системы нам нужен ваш номер телефона.\n\n"
            "Нажмите кнопку ниже, чтобы поделиться контактом:",
            reply_markup=back_keyboard
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
        try:
            friend_id_str = callback_data.split("_")[2]
        except IndexError:
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        
        # Обработка старых записей без user_id
        if friend_id_str.startswith("old_"):
            await query.edit_message_text(
                "ℹ️ Это старый формат записи друга. Пожалуйста, добавьте друга заново через поиск.",
                reply_markup=get_walk_with_friends_menu()
            )
            return ConversationHandler.END
        
        try:
            friend_id = int(friend_id_str)
        except ValueError:
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
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
        try:
            friend_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        
        if user_id not in user_data:
            await query.answer("Ошибка: данные пользователя не найдены", show_alert=True)
            return ConversationHandler.END
        
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
    
    elif callback_data == "choose_region":
        # Показываем список регионов России
        regions = get_regions_list()
        text = "🗺️ Выбрать регион\n\nВыберите регион из списка:\n\n"
        keyboard = []
        
        # Разбиваем на кнопки по 2 в ряд для компактности
        for i in range(0, len(regions), 2):
            row = []
            row.append(InlineKeyboardButton(
                regions[i],
                callback_data=f"select_region_{i}"
            ))
            if i + 1 < len(regions):
                row.append(InlineKeyboardButton(
                    regions[i + 1],
                    callback_data=f"select_region_{i + 1}"
                ))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("Назад", callback_data="find_location")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    elif callback_data.startswith("select_region_"):
        # Обработка выбора региона
        try:
            region_index = int(callback_data.split("_")[2])
            regions = get_regions_list()
            if 0 <= region_index < len(regions):
                selected_region = regions[region_index]
                
                # Сохраняем выбранный регион в контексте для дальнейшей обработки
                context.user_data['selected_region'] = selected_region
                
                # Показываем меню с кнопкой выбора района
                keyboard = [
                    [InlineKeyboardButton("Назад", callback_data="choose_region")],
                    [InlineKeyboardButton("🏘️ Выбрать район", callback_data="choose_district_in_region")]
                ]
                
                await query.edit_message_text(
                    f"🗺️ Регион: {selected_region}\n\n"
                    "Выберите район для поиска мест для прогулок:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.answer("Ошибка: некорректный регион", show_alert=True)
                return ConversationHandler.END
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при обработке выбора региона: {e}")
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        return ConversationHandler.END
    
    elif callback_data == "choose_district_in_region":
        # Выбор района в выбранном регионе
        selected_region = context.user_data.get('selected_region')
        if not selected_region:
            await query.answer("Ошибка: регион не выбран", show_alert=True)
            return ConversationHandler.END
        
        districts = get_districts_by_region(selected_region)
        
        text = f"🏘️ Выбрать район\n\n"
        text += f"Регион: {selected_region}\n\n"
        text += "Выберите район:\n\n"
        
        keyboard = []
        # Разбиваем на кнопки по 2 в ряд
        for i in range(0, len(districts), 2):
            row = []
            row.append(InlineKeyboardButton(
                districts[i],
                callback_data=f"select_district_{i}"
            ))
            if i + 1 < len(districts):
                row.append(InlineKeyboardButton(
                    districts[i + 1],
                    callback_data=f"select_district_{i + 1}"
                ))
            keyboard.append(row)
        
        # Сохраняем индекс региона для возврата
        region_index = get_regions_list().index(selected_region) if selected_region in get_regions_list() else 0
        # Вставляем кнопку "Назад" в начало
        keyboard.insert(0, [InlineKeyboardButton("Назад", callback_data=f"select_region_{region_index}")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    elif callback_data.startswith("select_district_"):
        # Обработка выбора района
        try:
            district_index = int(callback_data.split("_")[2])
            selected_region = context.user_data.get('selected_region')
            if not selected_region:
                await query.answer("Ошибка: регион не выбран", show_alert=True)
                return ConversationHandler.END
            
            districts = get_districts_by_region(selected_region)
            if 0 <= district_index < len(districts):
                selected_district = districts[district_index]
                
                # Сохраняем выбранный район в контексте
                context.user_data['selected_district'] = selected_district
                
                # Получаем список мест для прогулок
                walking_places = get_walking_places_by_district(selected_region, selected_district)
                
                text = f"🌳 Места для прогулок\n\n"
                text += f"Регион: {selected_region}\n"
                text += f"Район: {selected_district}\n\n"
                text += "Выберите место:\n\n"
                
                keyboard = []
                for i, place in enumerate(walking_places):
                    text += f"{i + 1}. {place}\n"
                    keyboard.append([InlineKeyboardButton(
                        f"{i + 1}. {place}",
                        callback_data=f"select_walking_place_{i}"
                    )])
                
                # Вставляем кнопку "Назад" в начало
                keyboard.insert(0, [InlineKeyboardButton("Назад", callback_data="choose_district_in_region")])
                
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.answer("Ошибка: некорректный район", show_alert=True)
                return ConversationHandler.END
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при обработке выбора района: {e}")
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        return ConversationHandler.END
    
    elif callback_data.startswith("select_walking_place_"):
        # Обработка выбора места для прогулок
        try:
            place_index = int(callback_data.split("_")[3])
            selected_region = context.user_data.get('selected_region')
            selected_district = context.user_data.get('selected_district')
            
            if not selected_region or not selected_district:
                await query.answer("Ошибка: регион или район не выбран", show_alert=True)
                return ConversationHandler.END
            
            walking_places = get_walking_places_by_district(selected_region, selected_district)
            if 0 <= place_index < len(walking_places):
                selected_place = walking_places[place_index]
                
                # Сохраняем информацию о месте в контексте
                context.user_data['selected_place'] = selected_place
                context.user_data['selected_place_full'] = f"{selected_region}, {selected_district}, {selected_place}"
                
                # Получаем информацию о месте
                place_info = get_place_info(selected_region, selected_district, selected_place)
                
                # Формируем текст с информацией о месте
                text = f"🌳 {selected_place}\n\n"
                text += f"📍 Регион: {selected_region}\n"
                text += f"🏘️ Район: {selected_district}\n\n"
                
                # Создаем клавиатуру с кнопками
                keyboard = []
                
                # Кнопка с ссылкой на Яндекс карты
                keyboard.append([InlineKeyboardButton(
                    "🗺️ Открыть на Яндекс картах",
                    url=place_info['yandex_map_url']
                )])
                
                # Кнопка "Поделиться местом с другом"
                keyboard.append([InlineKeyboardButton(
                    "📤 Поделиться местом с другом",
                    callback_data="share_place_with_friend"
                )])
                
                # Кнопка "Назад" в начало
                districts = get_districts_by_region(selected_region)
                district_index = districts.index(selected_district) if selected_district in districts else 0
                keyboard.insert(0, [InlineKeyboardButton("Назад", callback_data=f"select_district_{district_index}")])
                
                # Если есть фото места, отправляем его с подписью
                if place_info.get('photo_url'):
                    try:
                        await context.bot.send_photo(
                            chat_id=query.from_user.id,
                            photo=place_info['photo_url'],
                            caption=text,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        # Удаляем предыдущее сообщение
                        await query.delete_message()
                    except Exception as e:
                        logger.error(f"Ошибка при отправке фото места: {e}")
                        # Если не удалось отправить фото, отправляем текст
                        await query.edit_message_text(
                            text,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                else:
                    # Если фото нет, просто показываем текст
                    await query.edit_message_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
            else:
                await query.answer("Ошибка: некорректное место", show_alert=True)
                return ConversationHandler.END
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при обработке выбора места: {e}")
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        return ConversationHandler.END
    
    elif callback_data == "share_place_with_friend":
        # Поделиться местом с другом
        if user_id not in user_data:
            await query.answer("Ошибка: данные пользователя не найдены", show_alert=True)
            return ConversationHandler.END
        
        selected_place_full = context.user_data.get('selected_place_full')
        selected_place = context.user_data.get('selected_place')
        
        if not selected_place_full or not selected_place:
            await query.answer("Ошибка: место не выбрано", show_alert=True)
            return ConversationHandler.END
        
        friends_list = user_data[user_id].get('friends', [])
        
        if not friends_list:
            await query.edit_message_text(
                "📤 Поделиться местом\n\n"
                "У вас пока нет друзей.\n\n"
                "Используйте кнопку '🔍 Найти пользователя' чтобы найти и добавить друзей.",
                reply_markup=get_walk_with_friends_menu()
            )
            return ConversationHandler.END
        
        # Показываем список друзей для выбора
        text = f"📤 Поделиться местом\n\n"
        text += f"🌳 {selected_place}\n"
        text += f"📍 {selected_place_full}\n\n"
        text += "Выберите друга из списка:\n\n"
        
        keyboard = []
        for i, friend in enumerate(friends_list[:20], 1):  # Показываем максимум 20 друзей
            if isinstance(friend, dict):
                friend_id = friend.get('user_id')
                friend_name = friend.get('name', 'Друг')
                text += f"{i}. {friend_name}\n"
                keyboard.append([InlineKeyboardButton(
                    f"{i}. {friend_name}",
                    callback_data=f"share_place_to_{friend_id}"
                )])
        
        # Кнопка "Назад" в начало
        districts = get_districts_by_region(context.user_data.get('selected_region', ''))
        selected_district = context.user_data.get('selected_district', '')
        district_index = districts.index(selected_district) if selected_district in districts else 0
        place_index = 0  # Нужно найти индекс места
        walking_places = get_walking_places_by_district(context.user_data.get('selected_region', ''), selected_district)
        if selected_place in walking_places:
            place_index = walking_places.index(selected_place)
        keyboard.insert(0, [InlineKeyboardButton("Назад", callback_data=f"select_walking_place_{place_index}")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    elif callback_data.startswith("share_place_to_"):
        # Отправка места выбранному другу
        try:
            friend_id = int(callback_data.split("_")[3])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        
        selected_place_full = context.user_data.get('selected_place_full')
        selected_place = context.user_data.get('selected_place')
        selected_region = context.user_data.get('selected_region')
        selected_district = context.user_data.get('selected_district')
        
        if not selected_place_full or not selected_place:
            await query.answer("Ошибка: место не выбрано", show_alert=True)
            return ConversationHandler.END
        
        friend_info = user_data.get(friend_id)
        if not friend_info:
            await query.answer("Друг не найден", show_alert=True)
            return ConversationHandler.END
        
        # Получаем информацию о месте для Яндекс карт
        place_info = get_place_info(selected_region, selected_district, selected_place)
        
        # Имя пользователя, который делится местом
        sender_name = query.from_user.first_name or 'Друг'
        if query.from_user.username:
            sender_name += f" (@{query.from_user.username})"
        
        # Формируем сообщение для друга
        message_text = f"📤 {sender_name} поделился(ась) местом для прогулки:\n\n"
        message_text += f"🌳 {selected_place}\n"
        message_text += f"📍 {selected_place_full}\n\n"
        
        # Создаем клавиатуру с ссылкой на Яндекс карты
        share_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗺️ Открыть на Яндекс картах", url=place_info['yandex_map_url'])]
        ])
        
        try:
            # Отправляем сообщение другу
            await context.bot.send_message(
                chat_id=friend_id,
                text=message_text,
                reply_markup=share_keyboard
            )
            
            friend_display_name = friend_info.get('first_name', 'Друг')
            if friend_info.get('last_name'):
                friend_display_name += f" {friend_info['last_name']}"
            
            await query.edit_message_text(
                f"✅ Место успешно отправлено другу {friend_display_name}!",
                reply_markup=get_walk_with_friends_menu()
            )
            logger.info(f"Пользователь {user_id} поделился местом {selected_place} с другом {friend_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке места другу: {e}")
            await query.answer("❌ Не удалось отправить место. Возможно, друг заблокировал бота.", show_alert=True)
        
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
            reply_markup=get_main_menu(user_id)
        )
        return ConversationHandler.END
    
    elif callback_data == "find_pet_shop":
        await query.edit_message_text(
            "🛒 Найти зоомагазин\n\n"
            "Функция в разработке. Скоро здесь будет поиск ближайших зоомагазинов.",
            reply_markup=get_main_menu(user_id)
        )
        return ConversationHandler.END
    
    elif callback_data.startswith("select_user_"):
        # Обработка выбора пользователя из результатов поиска
        try:
            selected_user_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
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
            
            # Проверяем, есть ли уже запрос от текущего пользователя к выбранному
            # friend_requests структура: {target_user_id: [list of user_ids who sent requests]}
            has_request = user_id in friend_requests.get(selected_user_id, [])
            
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
        try:
            target_user_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        target_user = user_data.get(target_user_id)
        
        if target_user:
            display_name = target_user.get('first_name', 'Пользователь') or 'Пользователь'
            if target_user.get('last_name'):
                display_name += f" {target_user['last_name']}"
            
            # Сохраняем ID получателя в контексте
            context.user_data['message_target_user_id'] = target_user_id
            
            await query.edit_message_text(
                f"✉️ Написать сообщение\n\n"
                f"Получатель: {display_name}\n\n"
                f"Напишите текст сообщения, которое хотите отправить:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="walk_with_friends")]])
            )
            return WAITING_MESSAGE_TEXT
        else:
            await query.edit_message_text(
                "❌ Пользователь не найден.",
                reply_markup=get_walk_with_friends_menu()
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("add_friend_"):
        # Отправка запроса на добавление в друзья
        try:
            target_user_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        target_user = user_data.get(target_user_id)
        
        if target_user:
            if user_id not in user_data:
                user_data[user_id] = {
                    'walking_location': None,
                    'pet_photo_id': None,
                    'friends': [],
                    'username': query.from_user.username,
                    'first_name': query.from_user.first_name,
                    'last_name': query.from_user.last_name,
                    'phone_number': None,
                    'phone_verified': False
                }
                save_user_data()
            
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
                # Проверяем, не отправлен ли уже запрос
                if target_user_id not in friend_requests:
                    friend_requests[target_user_id] = []
                
                if user_id not in friend_requests[target_user_id]:
                    # Добавляем запрос: target_user_id получит запрос от user_id
                    friend_requests[target_user_id].append(user_id)
                    save_user_data()  # Сохраняем изменения
                    
                    # Пытаемся отправить уведомление пользователю
                    try:
                        current_user_name = query.from_user.first_name or 'Пользователь'
                        if query.from_user.username:
                            current_user_name += f" (@{query.from_user.username})"
                        
                        notification_text = (
                            f"👋 Новый запрос на дружбу!\n\n"
                            f"{current_user_name} хочет добавить вас в друзья.\n\n"
                            f"Используйте меню '👥 Гулять с друзьями' → '📥 Входящие запросы' чтобы подтвердить."
                        )
                        # Отправляем уведомление пользователю
                        await context.bot.send_message(chat_id=target_user_id, text=notification_text)
                        logger.info(f"Пользователь {user_id} отправил запрос на дружбу {target_user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления: {e}")
                    
                    await query.edit_message_text(
                        f"✅ Запрос на дружбу отправлен пользователю {friend_name}!\n\n"
                        f"Ожидайте подтверждения.",
                        reply_markup=get_walk_with_friends_menu()
                    )
                else:
                    await query.edit_message_text(
                        f"⏳ Запрос пользователю {friend_name} уже отправлен. Ожидайте подтверждения.",
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
    
    elif callback_data == "friend_requests_incoming":
        # Показываем входящие запросы на дружбу
        incoming_requests = friend_requests.get(user_id, [])
        
        if not incoming_requests:
            await query.edit_message_text(
                "📥 Входящие запросы на дружбу\n\n"
                "У вас нет входящих запросов на дружбу.",
                reply_markup=get_walk_with_friends_menu()
            )
        else:
            text = f"📥 Входящие запросы на дружбу ({len(incoming_requests)})\n\n"
            keyboard = []
            
            for requestor_id in incoming_requests:
                requestor_info = user_data.get(requestor_id, {})
                if requestor_info:
                    display_name = requestor_info.get('first_name', 'Пользователь')
                    if requestor_info.get('last_name'):
                        display_name += f" {requestor_info['last_name']}"
                    if requestor_info.get('username'):
                        display_name += f" (@{requestor_info['username']})"
                    
                    text += f"• {display_name}\n"
                    
                    keyboard.append([
                        InlineKeyboardButton(
                            f"✅ Принять {display_name[:20]}",
                            callback_data=f"accept_friend_{requestor_id}"
                        ),
                        InlineKeyboardButton(
                            f"❌ Отклонить",
                            callback_data=f"decline_friend_{requestor_id}"
                        )
                    ])
            
            keyboard.append([InlineKeyboardButton("Назад", callback_data="walk_with_friends")])
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("accept_friend_"):
        # Подтверждение запроса на дружбу
        try:
            requestor_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        
        if user_id not in user_data:
            user_data[user_id] = {
                'walking_location': None,
                'pet_photo_id': None,
                'friends': [],
                'tags': [],
                'age': None
            }
        
        requestor_info = user_data.get(requestor_id)
        
        if requestor_info:
            # Проверяем, что запрос действительно существует
            if user_id in friend_requests and requestor_id in friend_requests[user_id]:
                # Удаляем запрос
                friend_requests[user_id].remove(requestor_id)
                if not friend_requests[user_id]:
                    del friend_requests[user_id]
                
                # Добавляем в друзья (взаимно)
                # Добавляем requestor_id в друзья user_id
                if 'friends' not in user_data[user_id]:
                    user_data[user_id]['friends'] = []
                
                requestor_name = requestor_info.get('first_name', 'Пользователь')
                if requestor_info.get('username'):
                    requestor_name += f" (@{requestor_info['username']})"
                
                # Проверяем, не является ли уже другом
                is_already_friend = any(
                    isinstance(f, dict) and f.get('user_id') == requestor_id 
                    for f in user_data[user_id]['friends']
                )
                
                if not is_already_friend:
                    user_data[user_id]['friends'].append({
                        'user_id': requestor_id,
                        'name': requestor_name
                    })
                
                # Добавляем user_id в друзья requestor_id
                if requestor_id not in user_data:
                    user_data[requestor_id] = {
                        'walking_location': None,
                        'pet_photo_id': None,
                        'friends': [],
                        'username': requestor_info.get('username'),
                        'first_name': requestor_info.get('first_name'),
                        'last_name': requestor_info.get('last_name'),
                        'tags': [],
                        'age': None
                    }
                
                if 'friends' not in user_data[requestor_id]:
                    user_data[requestor_id]['friends'] = []
                
                current_user_name = query.from_user.first_name or 'Пользователь'
                if query.from_user.username:
                    current_user_name += f" (@{query.from_user.username})"
                
                is_current_user_friend = any(
                    isinstance(f, dict) and f.get('user_id') == user_id 
                    for f in user_data[requestor_id]['friends']
                )
                
                if not is_current_user_friend:
                    user_data[requestor_id]['friends'].append({
                        'user_id': user_id,
                        'name': current_user_name
                    })
                
                save_user_data()  # Сохраняем изменения
                
                # Отправляем уведомление пользователю, чей запрос был принят
                try:
                    notification_text = (
                        f"✅ Запрос на дружбу принят!\n\n"
                        f"{current_user_name} принял(а) ваш запрос на дружбу.\n\n"
                        f"Используйте меню '👥 Гулять с друзьями' → '👥 Мои друзья' чтобы увидеть список."
                    )
                    await context.bot.send_message(chat_id=requestor_id, text=notification_text)
                    logger.info(f"Пользователь {user_id} принял запрос на дружбу от {requestor_id}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления: {e}")
                
                await query.edit_message_text(
                    f"✅ Запрос на дружбу принят!\n\n"
                    f"Пользователь {requestor_name} добавлен в ваш список друзей.",
                    reply_markup=get_walk_with_friends_menu()
                )
            else:
                await query.edit_message_text(
                    "❌ Запрос не найден или уже обработан.",
                    reply_markup=get_walk_with_friends_menu()
                )
        else:
            await query.edit_message_text(
                "❌ Пользователь не найден.",
                reply_markup=get_walk_with_friends_menu()
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("decline_friend_"):
        # Отклонение запроса на дружбу
        try:
            requestor_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        requestor_info = user_data.get(requestor_id)
        
        if requestor_info:
            # Проверяем, что запрос действительно существует
            if user_id in friend_requests and requestor_id in friend_requests[user_id]:
                # Удаляем запрос
                friend_requests[user_id].remove(requestor_id)
                if not friend_requests[user_id]:
                    del friend_requests[user_id]
                
                save_user_data()  # Сохраняем изменения
                
                requestor_name = requestor_info.get('first_name', 'Пользователь')
                if requestor_info.get('username'):
                    requestor_name += f" (@{requestor_info['username']})"
                
                await query.edit_message_text(
                    f"❌ Запрос на дружбу от {requestor_name} отклонен.",
                    reply_markup=get_walk_with_friends_menu()
                )
            else:
                await query.edit_message_text(
                    "❌ Запрос не найден или уже обработан.",
                    reply_markup=get_walk_with_friends_menu()
                )
        else:
            await query.edit_message_text(
                "❌ Пользователь не найден.",
                reply_markup=get_walk_with_friends_menu()
            )
        return ConversationHandler.END
    
    elif callback_data == "invite_to_walk":
        # Рассылка приглашения всем подтвержденным друзьям
        if user_id not in user_data:
            await query.answer("Ошибка: данные пользователя не найдены", show_alert=True)
            return ConversationHandler.END
        
        friends_list = user_data[user_id].get('friends', [])
        
        if not friends_list:
            await query.edit_message_text(
                "🐕 Позвать гулять\n\n"
                "У вас пока нет друзей.\n\n"
                "Используйте кнопку '🔍 Найти пользователя' чтобы найти и добавить друзей.",
                reply_markup=get_walk_with_friends_menu()
            )
            return ConversationHandler.END
        
        # Получаем имя пользователя, который приглашает
        inviter_name = query.from_user.first_name or 'Друг'
        if query.from_user.username:
            inviter_name += f" (@{query.from_user.username})"
        
        # Текст сообщения
        message_text = f"Пойдем гуляять! Возьми вкусняшки! 🐕"
        
        # Отправляем сообщение всем подтвержденным друзьям
        sent_count = 0
        failed_count = 0
        
        for friend in friends_list:
            if isinstance(friend, dict):
                friend_id = friend.get('user_id')
                if friend_id:
                    friend_info = user_data.get(friend_id, {})
                    # Проверяем, что у друга подтвержден телефон
                    if friend_info.get('phone_verified', False):
                        try:
                            await context.bot.send_message(
                                chat_id=friend_id,
                                text=f"📢 {inviter_name} приглашает:\n\n{message_text}"
                            )
                            sent_count += 1
                        except Exception as e:
                            logger.error(f"Ошибка при отправке приглашения другу {friend_id}: {e}")
                            failed_count += 1
        
        # Формируем ответное сообщение
        if sent_count == 0:
            if failed_count == 0:
                result_text = (
                    "🐕 Позвать гулять\n\n"
                    "У вас нет друзей с подтвержденным номером телефона.\n\n"
                    "Добавьте друзей и попросите их подтвердить свой номер телефона."
                )
            else:
                result_text = (
                    f"🐕 Позвать гулять\n\n"
                    f"❌ Не удалось отправить приглашения друзьям.\n"
                    f"Возможно, некоторые друзья заблокировали бота."
                )
        else:
            result_text = (
                f"✅ Приглашение отправлено!\n\n"
                f"📤 Отправлено друзьям: {sent_count}"
            )
            if failed_count > 0:
                result_text += f"\n❌ Не удалось отправить: {failed_count}"
        
        await query.edit_message_text(
            result_text,
            reply_markup=get_walk_with_friends_menu()
        )
        return ConversationHandler.END
    
    # Обработчики для администратора
    elif callback_data == "admin_subscribers":
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        await query.edit_message_text(
            "👥 Управление подписчиками\n\n"
            "Выберите действие:",
            reply_markup=get_admin_menu()
        )
        return ConversationHandler.END
    
    elif callback_data == "admin_list_subscribers":
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        # Получаем список всех подписчиков
        subscribers = list(user_data.keys())
        
        if not subscribers:
            await query.edit_message_text(
                "👥 Список подписчиков\n\n"
                "Пока нет подписчиков.",
                reply_markup=get_admin_menu()
            )
        else:
            text = f"👥 Список подписчиков ({len(subscribers)})\n\n"
            keyboard = []
            
            # Показываем первых 50 подписчиков
            for subscriber_id in subscribers[:50]:
                subscriber_info = user_data.get(subscriber_id, {})
                display_name = subscriber_info.get('first_name', 'Пользователь') or 'Пользователь'
                if subscriber_info.get('last_name'):
                    display_name += f" {subscriber_info['last_name']}"
                if subscriber_info.get('username'):
                    display_name += f" (@{subscriber_info['username']})"
                
                # Показываем метки, если есть
                tags = subscriber_info.get('tags', [])
                tags_text = f" [{', '.join(tags)}]" if tags else ""
                
                keyboard.append([InlineKeyboardButton(
                    f"{display_name}{tags_text}",
                    callback_data=f"admin_view_subscriber_{subscriber_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("Назад", callback_data="admin_subscribers")])
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("admin_view_subscriber_"):
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        try:
            subscriber_id = int(callback_data.split("_")[3])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        subscriber_info = user_data.get(subscriber_id)
        
        if subscriber_info:
            display_name = subscriber_info.get('first_name', 'Пользователь') or 'Пользователь'
            if subscriber_info.get('last_name'):
                display_name += f" {subscriber_info['last_name']}"
            username = subscriber_info.get('username', 'не указан')
            walking_location = subscriber_info.get('walking_location', 'не указано')
            phone_number = subscriber_info.get('phone_number', 'не указан')
            phone_verified = subscriber_info.get('phone_verified', False)
            phone_status = "✅ подтвержден" if phone_verified else "❌ не подтвержден" if phone_number != 'не указан' else "не указан"
            age = subscriber_info.get('age', 'не указан')
            tags = subscriber_info.get('tags', [])
            tags_text = ", ".join(tags) if tags else "нет"
            
            text = (
                f"👤 Профиль подписчика\n\n"
                f"ID: {subscriber_id}\n"
                f"Имя: {display_name}\n"
                f"Username: @{username}\n"
                f"Возраст: {age}\n"
                f"📍 Где гуляет: {walking_location}\n"
                f"📱 Телефон: {phone_number} ({phone_status})\n"
                f"🏷️ Метки: {tags_text}\n\n"
                f"Выберите действие:"
            )
            
            await query.edit_message_text(
                text,
                reply_markup=get_subscriber_management_menu(subscriber_id)
            )
        else:
            await query.edit_message_text(
                "❌ Подписчик не найден.",
                reply_markup=get_admin_menu()
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("admin_delete_"):
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        try:
            subscriber_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        
        if subscriber_id in user_data:
            subscriber_info = user_data[subscriber_id]
            display_name = subscriber_info.get('first_name', 'Пользователь') or 'Пользователь'
            
            # Удаляем пользователя из user_data
            del user_data[subscriber_id]
            
            # Удаляем из friend_requests, если есть
            if subscriber_id in friend_requests:
                del friend_requests[subscriber_id]
            
            # Удаляем из списков друзей других пользователей
            for uid, user_info in user_data.items():
                if 'friends' in user_info:
                    user_info['friends'] = [
                        f for f in user_info['friends']
                        if isinstance(f, dict) and f.get('user_id') != subscriber_id
                    ]
            
            save_user_data()
            
            await query.edit_message_text(
                f"✅ Контакт {display_name} удален из базы данных.",
                reply_markup=get_admin_menu()
            )
        else:
            await query.edit_message_text(
                "❌ Подписчик не найден.",
                reply_markup=get_admin_menu()
            )
        return ConversationHandler.END
    
    elif callback_data.startswith("admin_message_"):
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        try:
            subscriber_id = int(callback_data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        subscriber_info = user_data.get(subscriber_id)
        
        if subscriber_info:
            display_name = subscriber_info.get('first_name', 'Пользователь') or 'Пользователь'
            if subscriber_info.get('last_name'):
                display_name += f" {subscriber_info['last_name']}"
            
            # Сохраняем ID получателя в контексте
            context.user_data['admin_message_target_user_id'] = subscriber_id
            
            await query.edit_message_text(
                f"✉️ Написать сообщение подписчику\n\n"
                f"Получатель: {display_name}\n\n"
                f"Напишите текст сообщения, которое хотите отправить:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data=f"admin_view_subscriber_{subscriber_id}")]])
            )
            return WAITING_ADMIN_MESSAGE_TEXT
        return ConversationHandler.END
    
    elif callback_data.startswith("admin_add_tag_"):
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        try:
            subscriber_id = int(callback_data.split("_")[3])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        subscriber_info = user_data.get(subscriber_id)
        
        if subscriber_info:
            # Сохраняем subscriber_id в контексте для обработки ввода метки
            context.user_data['admin_adding_tag_for'] = subscriber_id
            await query.edit_message_text(
                f"🏷️ Добавить метку\n\n"
                f"Введите название метки для пользователя {subscriber_info.get('first_name', 'Пользователь')}:\n\n"
                f"Примеры: VIP, Активный, Новый, Проблемный\n\n"
                f"Просто отправьте текст метки в чат:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data=f"admin_view_subscriber_{subscriber_id}")]])
            )
            return WAITING_ADMIN_TAG
        return ConversationHandler.END
    
    elif callback_data.startswith("admin_remove_tag_"):
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        try:
            subscriber_id = int(callback_data.split("_")[3])
        except (ValueError, IndexError):
            await query.answer("Ошибка: некорректный формат данных", show_alert=True)
            return ConversationHandler.END
        subscriber_info = user_data.get(subscriber_id)
        
        if subscriber_info:
            tags = subscriber_info.get('tags', [])
            if not tags:
                await query.edit_message_text(
                    f"🏷️ Удалить метку\n\n"
                    f"У пользователя нет меток.",
                    reply_markup=get_subscriber_management_menu(subscriber_id)
                )
            else:
                keyboard = []
                for tag in tags:
                    keyboard.append([InlineKeyboardButton(
                        f"❌ {tag}",
                        callback_data=f"admin_remove_tag_confirm_{subscriber_id}_{tag}"
                    )])
                keyboard.append([InlineKeyboardButton("Назад", callback_data=f"admin_view_subscriber_{subscriber_id}")])
                
                await query.edit_message_text(
                    f"🏷️ Удалить метку\n\n"
                    f"Выберите метку для удаления:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        return ConversationHandler.END
    
    elif callback_data.startswith("admin_remove_tag_confirm_"):
        # Проверяем, является ли пользователь администратором
        if not ADMIN_ID or str(user_id) != str(ADMIN_ID):
            await query.answer("У вас нет доступа к этой функции", show_alert=True)
            return ConversationHandler.END
        
        parts = callback_data.split("_")
        if len(parts) < 6:
            await query.edit_message_text(
                "❌ Ошибка: некорректный формат данных.",
                reply_markup=get_admin_menu()
            )
            return ConversationHandler.END
        
        try:
            subscriber_id = int(parts[4])
            tag = "_".join(parts[5:])  # На случай, если в метке есть подчеркивания
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при парсинге admin_remove_tag_confirm: {e}")
            await query.edit_message_text(
                "❌ Ошибка: некорректный формат данных.",
                reply_markup=get_admin_menu()
            )
            return ConversationHandler.END
        
        subscriber_info = user_data.get(subscriber_id)
        if subscriber_info:
            if 'tags' not in subscriber_info:
                subscriber_info['tags'] = []
            
            if tag in subscriber_info['tags']:
                subscriber_info['tags'].remove(tag)
                save_user_data()
                
                await query.edit_message_text(
                    f"✅ Метка '{tag}' удалена.",
                    reply_markup=get_subscriber_management_menu(subscriber_id)
                )
            else:
                await query.edit_message_text(
                    f"❌ Метка '{tag}' не найдена.",
                    reply_markup=get_subscriber_management_menu(subscriber_id)
                )
        return ConversationHandler.END
    
    return ConversationHandler.END


async def handle_location_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка текста для локации прогулок"""
    user_id = update.message.from_user.id
    location_text = update.message.text
    
    # Инициализируем данные пользователя, если их еще нет
    if user_id not in user_data:
        user_data[user_id] = {
            'walking_location': None,
            'pet_photo_id': None,
            'friends': [],
            'tags': [],
            'age': None
        }
    
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
    
    # Логируем для отладки
    logger.info(f"Поиск пользователя '{search_query}' от {user_id}. Всего пользователей в базе: {len(user_data)}")
    
    # Поиск пользователей
    found_users = []
    for uid, user_info in user_data.items():
        # Не показываем самого пользователя в результатах
        if uid == user_id:
            continue
        
        # Пропускаем пользователей без базовой информации
        if not user_info.get('first_name') and not user_info.get('username'):
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
        
        # Показываем список всех пользователей для отладки (можно убрать в продакшене)
        all_users_info = []
        for uid, user_info in user_data.items():
            if uid != user_id:
                name = user_info.get('first_name', 'Без имени')
                username = user_info.get('username', 'нет username')
                phone = user_info.get('phone_number', 'нет телефона')
                all_users_info.append(f"• {name} (@{username}) - {phone}")
        
        debug_info = ""
        if all_users_info:
            debug_info = f"\n\n📋 Доступные пользователи в базе ({len(all_users_info)}):\n" + "\n".join(all_users_info[:5])
            if len(all_users_info) > 5:
                debug_info += f"\n... и еще {len(all_users_info) - 5}"
        
        await update.message.reply_text(
            f"❌ Пользователь по {search_type} '{search_query}' не найден.\n\n"
            "Попробуйте:\n"
            "• Другой username (@username)\n"
            "• Имя или фамилию\n"
            "• Номер телефона\n\n"
            "Убедитесь, что пользователь зарегистрирован в боте и поделился контактом."
            + debug_info,
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
    """Обработка выбора локации по номеру и показ пользователей в этой локации"""
    try:
        choice = int(update.message.text)
        locations = context.user_data.get('locations', [])
        district = context.user_data.get('selected_district', '')
        user_id = update.message.from_user.id
        
        if 1 <= choice <= len(locations):
            selected_location = locations[choice - 1]
            
            # Ищем пользователей, которые указали эту локацию в своем профиле
            users_in_location = []
            for uid, user_info in user_data.items():
                # Пропускаем самого пользователя
                if uid == user_id:
                    continue
                
                # Получаем локацию пользователя
                user_location = user_info.get('walking_location', '')
                if user_location and selected_location.lower() in user_location.lower():
                    users_in_location.append({
                        'user_id': uid,
                        'first_name': user_info.get('first_name', 'Пользователь'),
                        'last_name': user_info.get('last_name', ''),
                        'username': user_info.get('username', ''),
                        'walking_location': user_location
                    })
            
            if not users_in_location:
                await update.message.reply_text(
                    f"📍 Локация: {selected_location}\n"
                    f"🏘️ Район: {district}\n\n"
                    "❌ В этой локации пока нет пользователей.\n\n"
                    "Пользователи появятся здесь, когда укажут эту локацию в своем профиле.",
                    reply_markup=get_find_location_menu()
                )
            else:
                text = (
                    f"📍 Локация: {selected_location}\n"
                    f"🏘️ Район: {district}\n\n"
                    f"👥 Найдено пользователей: {len(users_in_location)}\n\n"
                    "Выберите пользователя:"
                )
                
                keyboard = []
                for i, user in enumerate(users_in_location[:20], 1):  # Ограничиваем 20 результатами
                    display_name = user['first_name']
                    if user['last_name']:
                        display_name += f" {user['last_name']}"
                    if user['username']:
                        display_name += f" (@{user['username']})"
                    
                    keyboard.append([InlineKeyboardButton(
                        f"{i}. {display_name}",
                        callback_data=f"select_user_{user['user_id']}"
                    )])
                
                keyboard.append([InlineKeyboardButton("Назад", callback_data="find_location")])
                
                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
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
        
        # Удаляем клавиатуру с кнопкой - отвечаем на сообщение с контактом с ReplyKeyboardRemove
        # Это уберет клавиатуру из чата
        try:
            remove_message = await update.message.reply_text(
                ".",
                reply_markup=ReplyKeyboardRemove()
            )
            # Сразу удаляем служебное сообщение
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=remove_message.message_id)
            except Exception:
                pass  # Игнорируем ошибку удаления, главное что клавиатура убрана
        except Exception as e:
            logger.error(f"Ошибка при удалении клавиатуры: {e}")
            # Пытаемся альтернативным способом
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=".",
                    reply_markup=ReplyKeyboardRemove()
                )
            except Exception:
                pass
        
        # Теперь отправляем сообщение с кодом
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ Контакт получен!\n\n"
                f"📱 Ваш номер: +{phone_number}\n\n"
                f"🔐 Код подтверждения: {verification_code}\n\n"
                f"Введите этот код для подтверждения номера телефона:"
            )
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
                "❌ Код подтверждения истек. Пожалуйста, поделитесь контактом заново.\n\n"
                "Или вернитесь в главное меню:",
                reply_markup=get_main_menu(user_id)
            )
            del verification_codes[user_id]
            context.user_data.pop('waiting_verification', None)
            return ConversationHandler.END
        
        if entered_code == stored_code:
            # Код верный - подтверждаем номер
            # Инициализируем данные пользователя, если их еще нет
            if user_id not in user_data:
                user_data[user_id] = {
                    'walking_location': None,
                    'pet_photo_id': None,
                    'friends': [],
                    'tags': [],
                    'age': None
                }
            
            user_data[user_id]['phone_verified'] = True
            phone_number = verification_codes[user_id]['phone']
            user_data[user_id]['phone_number'] = phone_number
            save_user_data()
            
            # Удаляем код из временного хранилища
            del verification_codes[user_id]
            context.user_data.pop('waiting_verification', None)
            
            await update.message.reply_text(
                f"✅ Номер телефона подтвержден!\n\n"
                f"📱 Ваш номер: +{phone_number}\n\n"
                f"Теперь вы можете использовать все функции бота.",
                reply_markup=get_main_menu(user_id)
            )
        else:
            await update.message.reply_text(
                "❌ Неверный код подтверждения. Попробуйте еще раз:"
            )
            return WAITING_VERIFICATION_CODE
    else:
        await update.message.reply_text(
            "❌ Код подтверждения не найден. Пожалуйста, поделитесь контактом заново.\n\n"
            "Или вернитесь в главное меню:",
            reply_markup=get_main_menu(user_id)
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
            'friends': [],
            'username': update.message.from_user.username,
            'first_name': update.message.from_user.first_name,
            'last_name': update.message.from_user.last_name,
            'phone_number': None,
            'phone_verified': False,
            'tags': [],
            'age': None
        }
        save_user_data()
    
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
    
    # Проверяем, ожидается ли ввод метки администратором
    if context.user_data.get('admin_adding_tag_for'):
        subscriber_id = context.user_data.get('admin_adding_tag_for')
        
        # Проверяем, является ли пользователь администратором
        if ADMIN_ID and str(user_id) == str(ADMIN_ID):
            tag = update.message.text.strip()
            
            if subscriber_id in user_data:
                subscriber_info = user_data[subscriber_id]
                if 'tags' not in subscriber_info:
                    subscriber_info['tags'] = []
                
                if tag and tag not in subscriber_info['tags']:
                    subscriber_info['tags'].append(tag)
                    save_user_data()
                    
                    display_name = subscriber_info.get('first_name', 'Пользователь') or 'Пользователь'
                    await update.message.reply_text(
                        f"✅ Метка '{tag}' добавлена пользователю {display_name}.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад к профилю", callback_data=f"admin_view_subscriber_{subscriber_id}")]])
                    )
                elif tag in subscriber_info['tags']:
                    await update.message.reply_text(
                        f"ℹ️ Метка '{tag}' уже есть у этого пользователя.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад к профилю", callback_data=f"admin_view_subscriber_{subscriber_id}")]])
                    )
                else:
                    await update.message.reply_text(
                        "❌ Метка не может быть пустой.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data=f"admin_view_subscriber_{subscriber_id}")]])
                    )
            else:
                await update.message.reply_text(
                    "❌ Подписчик не найден.",
                    reply_markup=get_admin_menu()
                )
            
            # Очищаем состояние
            context.user_data.pop('admin_adding_tag_for', None)
        return
    
    # Проверяем, ожидается ли ввод текста сообщения для отправки пользователю
    if context.user_data.get('message_target_user_id'):
        target_user_id = context.user_data.get('message_target_user_id')
        message_text = update.message.text
        
        target_user = user_data.get(target_user_id)
        if target_user:
            sender_name = update.message.from_user.first_name or 'Пользователь'
            if update.message.from_user.username:
                sender_name += f" (@{update.message.from_user.username})"
            
            try:
                # Отправляем сообщение получателю
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"✉️ Сообщение от {sender_name}:\n\n{message_text}"
                )
                
                target_display_name = target_user.get('first_name', 'Пользователь') or 'Пользователь'
                await update.message.reply_text(
                    f"✅ Сообщение отправлено пользователю {target_display_name}!",
                    reply_markup=get_walk_with_friends_menu()
                )
                logger.info(f"Пользователь {user_id} отправил сообщение {target_user_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения: {e}")
                await update.message.reply_text(
                    f"❌ Не удалось отправить сообщение. Возможно, пользователь заблокировал бота или удалил аккаунт.",
                    reply_markup=get_walk_with_friends_menu()
                )
        else:
            await update.message.reply_text(
                "❌ Пользователь не найден.",
                reply_markup=get_walk_with_friends_menu()
            )
        
        # Очищаем состояние
        context.user_data.pop('message_target_user_id', None)
        return
    
    # Проверяем, ожидается ли ввод текста сообщения от администратора
    if context.user_data.get('admin_message_target_user_id'):
        target_user_id = context.user_data.get('admin_message_target_user_id')
        message_text = update.message.text
        
        # Проверяем, является ли пользователь администратором
        if ADMIN_ID and str(user_id) == str(ADMIN_ID):
            target_user = user_data.get(target_user_id)
            if target_user:
                try:
                    # Отправляем сообщение получателю
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"📩 Сообщение от администратора:\n\n{message_text}"
                    )
                    
                    target_display_name = target_user.get('first_name', 'Пользователь') or 'Пользователь'
                    await update.message.reply_text(
                        f"✅ Сообщение отправлено подписчику {target_display_name}!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад к профилю", callback_data=f"admin_view_subscriber_{target_user_id}")]])
                    )
                    logger.info(f"Администратор {user_id} отправил сообщение подписчику {target_user_id}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения администратора: {e}")
                    await update.message.reply_text(
                        f"❌ Не удалось отправить сообщение. Возможно, подписчик заблокировал бота или удалил аккаунт.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад к профилю", callback_data=f"admin_view_subscriber_{target_user_id}")]])
                    )
            else:
                await update.message.reply_text(
                    "❌ Подписчик не найден.",
                    reply_markup=get_admin_menu()
                )
            
            # Очищаем состояние
            context.user_data.pop('admin_message_target_user_id', None)
        return
    
    # Если пользователь не в состоянии ожидания, показываем главное меню
    await update.message.reply_text(
        "Выберите действие из меню:",
        reply_markup=get_main_menu(user_id)
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
                CallbackQueryHandler(button_callback, pattern="^(my_walking_location|write_friend|choose_district|search_user|share_contact|admin_add_tag_|write_to_|admin_message_)")
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
                ],
                WAITING_ADMIN_TAG: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message),
                    CallbackQueryHandler(button_callback, pattern="^admin_view_subscriber_")
                ],
                WAITING_MESSAGE_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message),
                    CallbackQueryHandler(button_callback, pattern="^walk_with_friends$")
                ],
                WAITING_ADMIN_MESSAGE_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message),
                    CallbackQueryHandler(button_callback, pattern="^admin_view_subscriber_")
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
        application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
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
