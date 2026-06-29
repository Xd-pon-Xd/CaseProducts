import asyncio
import logging
import sys
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from LLM_Parser import parse_ingredients_with_llm, parse_ingredients_from_image
import database as db

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_errors.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден! Создайте файл .env и добавьте токен.")

dp = Dispatcher()


class RecipeStates(StatesGroup):
    waiting_for_name_confirmation = State()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="➕ Добавить рецепт"), KeyboardButton(text="📊 Мой список продуктов")],
        [KeyboardButton(text="📖 Как это работает?"), KeyboardButton(text="💡 Примеры ввода")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_clear_inline_kb() -> InlineKeyboardMarkup:
    btn = InlineKeyboardButton(text="🗑️ Очистить весь список", callback_data="clear_list")
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


def get_confirm_kb(dish: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Сохранить как «{dish}»", callback_data="confirm_save"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_save"),
    ]])


def _format_ingredients(items: list) -> str:
    lines = []
    for item in items:
        name = item.get("name", "Неизвестно").capitalize()
        amount = item.get("amount", 1.0)
        unit = item.get("unit", "шт")
        if isinstance(amount, float) and amount.is_integer():
            amount = int(amount)
        lines.append(f"🔹 <b>{name}</b> — <code>{amount} {unit}</code>")
    return "\n".join(lines)


async def _show_confirmation(status_msg: Message, dish: str, ingredients: list, state: FSMContext):
    """Показывает результат парсинга и кнопки подтверждения названия."""
    await state.update_data(dish=dish, ingredients=ingredients)
    await state.set_state(RecipeStates.waiting_for_name_confirmation)

    result = f"<b>📋 Найдены ингредиенты:</b>\n────────────────────\n"
    result += _format_ingredients(ingredients)
    result += f"\n────────────────────\n"
    result += f"Сохранить как <b>«{dish}»</b>?\nИли введи своё название:"

    await status_msg.edit_text(result, reply_markup=get_confirm_kb(dish))


@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    db.add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "unknown",
        first_name=message.from_user.first_name,
    )
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}! ✨\n\n"
        f"Пришли мне рецепт — текстом, ссылкой на сайт или фото. "
        f"Я извлеку ингредиенты, предложу название и соберу корзину для магазина.\n\n"
        f"Нажми <b>'➕ Добавить рецепт'</b> или просто отправь что хочешь.",
        reply_markup=get_main_keyboard(),
    )


@dp.message(F.text == "➕ Добавить рецепт")
async def start_adding_recipe(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🍳 Отправь мне рецепт:\n\n"
        "• Текст с ингредиентами\n"
        "• Ссылку на кулинарный сайт\n"
        "• Фото или скриншот рецепта\n\n"
        "<i>Я сам определю название блюда и предложу его тебе.</i>"
    )


@dp.message(F.text == "📊 Мой список продуктов")
async def show_shopping_list_handler(message: Message) -> None:
    user_id = message.from_user.id
    recipes = db.get_user_recipes(user_id)
    products = db.get_aggregated_ingredients(user_id)

    if not products:
        await message.answer("🛒 <b>Твой список продуктов пуст.</b>\nОтправь мне рецепт!")
        return

    response_text = "<b>📋 Корзина на основе блюд:</b>\n"
    response_text += ", ".join(f"<i>{r}</i>" for r in recipes) + "\n"
    response_text += "────────────────────\n<b>🛒 Итоговый список покупок:</b>\n\n"

    for item in products:
        name = item["name"].capitalize()
        amount = item["amount"]
        unit = item["unit"]
        if isinstance(amount, float):
            amount = round(amount, 2)
            if amount.is_integer():
                amount = int(amount)
        response_text += f"✅ <b>{name}</b> — <code>{amount} {unit}</code>\n"

    response_text += "────────────────────\n"
    await message.answer(response_text, reply_markup=get_clear_inline_kb())


@dp.message(Command("help"))
@dp.message(F.text == "📖 Как это работает?")
async def command_help_handler(message: Message) -> None:
    await message.answer(
        "<b>🤖 Как пользоваться ботом:</b>\n\n"
        "1️⃣ Отправь рецепт текстом, ссылкой или фото.\n"
        "2️⃣ ИИ извлечёт ингредиенты и предложит название.\n"
        "3️⃣ Подтверди название или введи своё.\n"
        "4️⃣ В '📊 Мой список продуктов' — итоговая корзина со всеми рецептами.\n\n"
        "<i>Одинаковые ингредиенты из разных рецептов суммируются автоматически.</i>"
    )


@dp.message(F.text == "💡 Примеры ввода")
async def toggle_tips_handler(message: Message) -> None:
    await message.answer(
        "<b>📝 Что можно отправить:</b>\n\n"
        "• Текст рецепта\n"
        "• Ссылку на кулинарный сайт\n"
        "• Фото или скриншот рецепта"
    )


# --- Подтверждение названия ---

@dp.message(RecipeStates.waiting_for_name_confirmation, F.text)
async def process_name_confirmation(message: Message, state: FSMContext):
    custom_name = message.text.strip()
    data = await state.get_data()
    ingredients = data.get("ingredients", [])

    db.save_ingredients(message.from_user.id, custom_name, ingredients)
    await state.clear()
    await message.answer(f"💾 <b>Сохранено как «{custom_name}»!</b>")


@dp.callback_query(F.data == "confirm_save", RecipeStates.waiting_for_name_confirmation)
async def confirm_save_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    dish = data.get("dish", "Новый рецепт")
    ingredients = data.get("ingredients", [])

    db.save_ingredients(callback.from_user.id, dish, ingredients)
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"💾 <b>Сохранено как «{dish}»!</b>")


@dp.callback_query(F.data == "cancel_save", RecipeStates.waiting_for_name_confirmation)
async def cancel_save_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Сохранение отменено.")


@dp.callback_query(F.data == "clear_list")
async def clear_list_callback(callback: CallbackQuery):
    db.clear_user_products(callback.from_user.id)
    await callback.answer("Список покупок очищен!")
    await callback.message.edit_text("🗑️ <b>Ваш список покупок полностью очищен.</b>")


# --- Обработка фото ---

@dp.message(RecipeStates.waiting_for_name_confirmation, F.photo)
@dp.message(F.photo)
async def process_photo_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    temp_path = f"temp_user_{message.from_user.id}.jpg"
    status_msg = await message.answer("👁️ <b>ИИ анализирует изображение...</b>")

    try:
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        await message.bot.download_file(file_info.file_path, temp_path)

        dish, ingredients = await parse_ingredients_from_image(temp_path)

        if not ingredients:
            await status_msg.edit_text(
                "❌ Не удалось распознать ингредиенты на фото. "
                "Попробуй сделать фото чётче или отправить текст вручную."
            )
            return

        await _show_confirmation(status_msg, dish, ingredients, state)

    except Exception as e:
        logger.error("Ошибка при обработке фото: %s", e)
        await status_msg.edit_text("❌ Ошибка при обработке картинки. Попробуй ещё раз.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# --- Обработка текста и ссылок ---

@dp.message(F.text)
async def process_recipe_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    status_msg = await message.answer("🧠 <b>ИИ анализирует запрос...</b>")

    try:
        dish, ingredients = await parse_ingredients_with_llm(message.text)

        if not ingredients:
            await status_msg.edit_text(
                "❌ Не удалось найти ингредиенты. "
                "Убедись, что это кулинарный рецепт."
            )
            return

        await _show_confirmation(status_msg, dish, ingredients, state)

    except Exception as e:
        logger.error("Ошибка в обработчике текста: %s", e)
        await status_msg.edit_text("⏳ Сервер занят. Попробуйте ещё раз.")


async def main() -> None:
    db.init_db()
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
