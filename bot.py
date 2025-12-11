from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

# Загрузка токена вашего бота из config.py
TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'

async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("Мой профиль", callback_data='profile')],
        [InlineKeyboardButton("Гулять с друзьями", callback_data='friends')],
        [InlineKeyboardButton("Найти локацию для прогулки", callback_data='location')],
        [InlineKeyboardButton("Найти ветклинику", callback_data='vet_clinic')],
        [InlineKeyboardButton("Найти зоомагазин", callback_data='pet_shop')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Добро пожаловать!', reply_markup=reply_markup)

async def button(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'profile':
        profile_keyboard = [
            [InlineKeyboardButton("Где я гуляю", callback_data='walk_location')],
            [InlineKeyboardButton("Фото питомца", callback_data='pet_photo')],
            [InlineKeyboardButton("Назад", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(profile_keyboard)
        await query.edit_message_text(text="Ваш профиль:", reply_markup=reply_markup)
        
    elif query.data == 'friends':
        friends_keyboard = [
            [InlineKeyboardButton("Написать другу", callback_data='write_friend')],
            [InlineKeyboardButton("Назад", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(friends_keyboard)
        await query.edit_message_text(text="Гулять с друзьями:", reply_markup=reply_markup)
        
    elif query.data == 'location':
        location_keyboard = [
            [InlineKeyboardButton("Выбрать район", callback_data='select_district')],
            [InlineKeyboardButton("Выбрать локацию", callback_data='select_place')],
            [InlineKeyboardButton("Назад", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(location_keyboard)
        await query.edit_message_text(text="Найти локацию для прогулки:", reply_markup=reply_markup)
        
    else:
        await query.edit_message_text(text=f"Выполняется действие {query.data}")

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    
    print("Bot started!")
    application.run_polling()

if __name__ == '__main__':
    main()
