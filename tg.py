import asyncio
import logging
import sys
import io
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
# Подключаем функцию парсинга из LLM_Parser.py
from LLM_Parser import parse_ingredients_with_llm
# Подключаем database.py
import database as db

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = "8504116605:AAHEFELkrW1VRd6lUgSZ7eRgQrFxCFkA8zI"
dp = Dispatcher()

# --- СОЗДАЕМ КНОПКИ ДЛЯ МЕНЮ ---
def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📖 Как это работает?"), KeyboardButton(text="💡 Примеры ввода")],
        [KeyboardButton(text="📊 Мой список продуктов")]
    ]
    # resize_keyboard=True делает кнопки аккуратными, а не на пол-экрана
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Инлайн-кнопка для очистки списка
def get_clear_inline_kb() -> InlineKeyboardMarkup:
    inline_btn = InlineKeyboardButton(text="🗑️ Очистить весь список", callback_data="clear_list")
    return InlineKeyboardMarkup(inline_keyboard=[[inline_btn]])

# 1. ХЭНДЛЕР НА /start
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    # Регистрация пользователя в БД
    db.add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "unknown",
        first_name=message.from_user.first_name
    )

    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}! ✨\n\n"
        f"Я твой умный кулинарный ассистент на базе нейросети {html.code('Gemma 3 / Llama')}.\n\n"
        f"🟢 <b>Что я умею?</b>\n"
        f"Ты отправляешь мне скопированный рецепт (или даже кучу мусорного текста с сайта), "
        f"а я вытаскиваю из него чистый список продуктов, перевожу их в начальную форму "
        f"и бережно считаю количество.\n\n"
        f"👇 Воспользуйся меню или просто пришли мне текст рецепта!",
        reply_markup=get_main_keyboard()
    )

# 2. ХЭНДЛЕР НА /help ИЛИ КНОПКУ "Как это работает"
@dp.message(Command("help"))
@dp.message(F.text == "📖 Как это работает?")
async def command_help_handler(message: Message) -> None:
    help_text = (
        "<b>🤖 Как пользоваться ботом:</b>\n\n"
        "1️⃣ Найди любой рецепт в интернете.\n"
        "2️⃣ Скопируй содержание страницы.\n"
        "3️⃣ Отправь текст мне сообщением.\n\n"
        "🔄 <i>Запросы обрабатываются через бесплатные ИИ-серверы, поэтому иногда разбор может занять до 5-10 секунд. Если я выдал ошибку — просто отправь текст еще раз!</i>"
    )
    await message.answer(help_text)

# 3. ХЭНДЛЕР НА КНОПКУ "Примеры ввода"
@dp.message(F.text == "💡 Примеры ввода")
async def toggle_tips_handler(message: Message) -> None:
    tips_text = (
        "<b>📝 Нейросеть поймет любой из этих вариантов:</b>\n\n"
        "• <code>Масло сливочное для смазки сковороды — 50г</code>\n"
        "  <i>(ИИ поймет, что продукт — 'масло сливочное', а 'для смазки' — отбросит)</i>\n\n"
        "• <code>Яйца — 3 шт, мука — около 1,5 стакана (200г)</code>\n"
        "  <i>(ИИ приведет к начальной форме: 'яйцо', и выберет точный вес муки)</i>\n\n"
        "• <code>Соль — на кончике ножа или щепотка</code>\n"
        "  <i>(ИИ переведет абстрактные величины в понятный формат)</i>"
    )
    await message.answer(tips_text)

# 4. ХЭНДЛЕР НА КНОПКУ "Мой список продуктов"
@dp.message(F.text == "📊 Мой список продуктов")
async def show_shopping_list_handler(message: Message) -> None:
    user_id = message.from_user.id
    products = db.get_aggregated_ingredients(user_id)
    
    if not products:
        await message.answer("🛒 <b>Твой список продуктов пока пуст.</b>\nПришли мне какой-нибудь рецепт, чтобы наполнить его!")
        return
        
    response_text = "<b>🛒 Ваш суммированный список покупок:</b>\n"
    response_text += "────────────────────\n"
    
    for item in products:
        name = item['name'].capitalize()
        amount = item['amount']
        unit = item['unit']
        
        if isinstance(amount, float) and amount.is_integer():
            amount = int(amount)
            
        response_text += f"✅ <b>{name}</b> — <code>{amount} {unit}</code>\n"
        
    response_text += "────────────────────\n"
    
    await message.answer(response_text, reply_markup=get_clear_inline_kb())

# --- ОБРАБОТКА НАЖАТИЯ НА КНОПКУ ОЧИСТКИ ---
@dp.callback_query(F.data == "clear_list")
async def clear_list_callback(callback: CallbackQuery):
    db.clear_user_products(callback.from_user.id)
    # Отправляем всплывающее уведомление в ТГ
    await callback.answer("Список покупок успешно очищен!")
    # Меняем текст сообщения
    await callback.message.edit_text("🗑️ <b>Ваш список покупок был полностью очищен.</b>")

# Заглушка под EasyOCR
@dp.message(F.photo)
async def process_photo_handler(message: Message) -> None:
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    await asyncio.sleep(1) 
    await message.answer(
        "📸 Вижу твою фотку! Модуль EasyOCR уже на подходе. "
        "Совсем скоро ты сможешь загружать сюда рукописные рецепты, и я их распаршу!"
    )

@dp.message(F.text)
async def process_recipe_handler(message: Message) -> None:
    raw_text = message.text
    user_id = message.from_user.id
    # Отправляем статус "typing", чтобы пользователь видел анимацию
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # Первое статусное сообщение, чтобы пользователь понимал, что процесс идет
    status_msg = await message.answer("🧠 <b>Нейросеть изучает текст рецепта...</b>\n<i>Это может занять несколько секунд.</i>")
    
    try:
        parsed_ingredients = await parse_ingredients_with_llm(raw_text)
        
        if not parsed_ingredients:
            # Если ИИ вернул пустой список (например, текст вообще не про еду)
            await status_msg.edit_text(
                "❌ <b>Не удалось найти ингредиенты.</b>\n\n"
                "Убедись, что в тексте есть продукты и их количества, или попробуй перефразировать ввод."
            )
            return
        
        db.save_ingredients(user_id, parsed_ingredients)
            
        # Формируем финальный ответ
        response_text = "<b>📋 Ингредиенты успешно извлечены:</b>\n"
        response_text += "────────────────────\n"
        
        for item in parsed_ingredients:
            name = item.get('name', 'Неизвестный продукт').capitalize()
            amount = item.get('amount', 1.0)
            unit = item.get('unit', 'шт')
            
            # Форматируем числа (убираем .0, если число целое)
            if isinstance(amount, float) and amount.is_integer():
                amount = int(amount)
                
            response_text += f"🔸 <b>{name}</b> — <code>{amount} {unit}</code>\n"
            
        
        # Редактируем старое сообщение вместо отправки нового, чтобы не спамить в чате
        await status_msg.edit_text(response_text)
        
    except Exception as e:
        logging.error(f"Ошибка в хэндлере ТГ: {e}")
        # Сообщение на случай перегрузки бесплатных серверов
        await status_msg.edit_text("⏳ Сервер ИИ занят, попробуйте отправить текст еще раз через пару секунд!")

async def main() -> None:
    db.init_db()
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("Бот успешно запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())