import asyncio
import logging
import sys
import io
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
# Импортируем инструменты состояний
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
# Подключаем функцию парсинга из LLM_Parser.py
from LLM_Parser import parse_ingredients_with_llm
# Подключаем database.py
import database as db

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = "8504116605:AAHEFELkrW1VRd6lUgSZ7eRgQrFxCFkA8zI"
dp = Dispatcher()

# --- ОПРЕДЕЛЯЕМ СОСТОЯНИЯ БОТА ---
class RecipeStates(StatesGroup):
    waiting_for_recipe_name = State() # Бот ждет название блюда
    waiting_for_recipe_text = State() # Бот ждет сам текст рецепта

# --- СОЗДАЕМ КНОПКИ ДЛЯ МЕНЮ ---
def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="➕ Добавить рецепт"), KeyboardButton(text="📊 Мой список продуктов")],
        [KeyboardButton(text="📖 Как это работает?"), KeyboardButton(text="💡 Примеры ввода")]
    ]
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
        f"Я умный кулинарный органайзер. Теперь я умею группировать продукты по блюдам "
        f"и автоматически переводить веса (килограммы в граммы, ложки в объемы) при суммировании!\n\n"
        f"Нажми кнопку <b>'➕ Добавить рецепт'</b>, чтобы начать.",
        reply_markup=get_main_keyboard()
    )

# --- НАЧАЛО СЦЕНАРИЯ ---
@dp.message(F.text == "➕ Добавить рецепт")
async def start_adding_recipe(message: Message, state: FSMContext):
    await message.answer("🍳 <b>Введите название блюда</b> (напр. <i>Борщ, Блины, Торт Наполеон</i>):")
    # Переключаем бота в состояние ожидания имени
    await state.set_state(RecipeStates.waiting_for_recipe_name)

# --- СЛЕДУЮЩИЙ ШАГ: ПОЛУЧИЛИ ИМЯ, ЖДЕМ ТЕКСТ ---
@dp.message(RecipeStates.waiting_for_recipe_name)
async def process_recipe_name(message: Message, state: FSMContext):
    recipe_name = message.text.strip()
    # Сохраняем имя во временную память aiogram
    await state.update_data(chosen_recipe_name=recipe_name)
    
    await message.answer(f"📥 Отлично! Теперь отправь мне <b>сырой текст ингредиентов</b> для блюда '{html.bold(recipe_name)}':")
    # Переключаем в состояние ожидания рецепта
    await state.set_state(RecipeStates.waiting_for_recipe_text)

# --- ФИНАЛ СЦЕНАРИЯ: ИИ + ЗАПИСЬ С НАЗВАНИЕМ БЛЮДА ---
@dp.message(RecipeStates.waiting_for_recipe_text)
async def process_recipe_text(message: Message, state: FSMContext):
    raw_text = message.text
    user_id = message.from_user.id
    
    # Достаем сохраненное имя блюда из контекста FSM
    user_data = await state.get_data()
    recipe_name = user_data.get('chosen_recipe_name', 'Без названия')
    
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    status_msg = await message.answer(f"🧠 <b>ИИ анализирует ингредиенты для '{recipe_name}'...</b>")
    
    try:
        parsed_ingredients = await parse_ingredients_with_llm(raw_text)
        
        if not parsed_ingredients:
            await status_msg.edit_text("❌ Не удалось найти ингредиенты. Попробуйте еще раз.")
            return
            
        # СОХРАНЯЕМ В БД ВМЕСТЕ С НАЗВАНИЕМ БЛЮДА
        db.save_ingredients(user_id, recipe_name, parsed_ingredients)
        
        response_text = f"<b>📋 Добавлено в рецепт '{recipe_name}':</b>\n"
        response_text += "────────────────────\n"
        for item in parsed_ingredients:
            name = item.get('name', 'Неизвестно').capitalize()
            amount = item.get('amount', 1.0)
            unit = item.get('unit', 'шт')
            if isinstance(amount, float) and amount.is_integer():
                amount = int(amount)
            response_text += f"🔹 <b>{name}</b> — <code>{amount} {unit}</code>\n"
            
        response_text += "────────────────────\n"
        response_text += "💾 <i>Данные успешно сохранены! Можете добавить еще один рецепт или открыть итоговый список.</i>"
        
        await status_msg.edit_text(response_text)
        # СБРАСЫВАЕМ СОСТОЯНИЕ, БОТ СНОВА ГОТОВ КО ВСЕМУ
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка в хэндлере: {e}")
        await status_msg.edit_text("⏳ Ошибка ИИ сервера. Попробуйте отправить текст рецепта еще раз.")

# --- ВЫВОД СПИСКА ПОКУПОК С УМНЫМ СУММИРОВАНИЕМ ВЕСОВ И СПИСКОМ БЛЮД ---
@dp.message(F.text == "📊 Мой список продуктов")
async def show_shopping_list_handler(message: Message) -> None:
    user_id = message.from_user.id
    
    # Получаем список блюд, которые ввел пользователь
    recipes = db.get_user_recipes(user_id)
    products = db.get_aggregated_ingredients(user_id)
    
    if not products:
        await message.answer("🛒 <b>Твой список продуктов пуст.</b>\nНажми '➕ Добавить рецепт'!")
        return
        
    # Формируем шапку со списком блюд
    response_text = "<b>📋 Корзина собрана на основе блюд:</b>\n"
    response_text += ", ".join([f"<i>{r}</i>" for r in recipes]) + "\n"
    response_text += "────────────────────\n"
    response_text += "<b>🛒 Итоговый список покупок (с переводом весов):</b>\n\n"
    
    for item in products:
        name = item['name'].capitalize()
        amount = item['amount']
        unit = item['unit']
        
        # Красиво округляем, чтобы не было 10.0000001
        if isinstance(amount, float):
            amount = round(amount, 2)
            if amount.is_integer():
                amount = int(amount)
                
        response_text += f"✅ <b>{name}</b> — <code>{amount} {unit}</code>\n"
        
    response_text += "────────────────────\n"
    
    await message.answer(response_text, reply_markup=get_clear_inline_kb())

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

# Этот хэндлер ловит рецепты, которые прислали напрямую (без нажатия кнопки)
@dp.message(F.text)
async def process_recipe_handler(message: Message) -> None:
    raw_text = message.text
    user_id = message.from_user.id
    
    # Задаем дефолтное имя, так как пользователь не нажимал кнопку
    recipe_name = "Быстрый рецепт"
    
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    status_msg = await message.answer("🧠 <b>ИИ анализирует рецепт...</b>")
    
    try:
        parsed_ingredients = await parse_ingredients_with_llm(raw_text)
        
        if not parsed_ingredients:
            await status_msg.edit_text("❌ Не удалось найти ингредиенты.")
            return
            
        db.save_ingredients(user_id, recipe_name, parsed_ingredients)
        
        response_text = f"<b>📋 Добавлено в '{recipe_name}':</b>\n"
        response_text += "────────────────────\n"
        for item in parsed_ingredients:
            name = item.get('name', 'Неизвестно').capitalize()
            amount = item.get('amount', 1.0)
            unit = item.get('unit', 'шт')
            
            if isinstance(amount, float) and amount.is_integer():
                amount = int(amount)
            response_text += f"🔹 <b>{name}</b> — <code>{amount} {unit}</code>\n"
            
        response_text += "────────────────────\n"
        response_text += "💾 <i>Сохранено! Вы можете посмотреть общий итог в меню '📊 Мой список продуктов'.</i>"
        
        await status_msg.edit_text(response_text)
        
    except Exception as e:
        logging.error(f"Ошибка в быстром хэндлере ТГ: {e}")
        await status_msg.edit_text("⏳ Сервер ИИ занят, попробуйте отправить текст еще раз через пару секунд!")

async def main() -> None:
    db.init_db()
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("Бот успешно запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())