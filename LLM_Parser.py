import json
import base64
import logging
import asyncio
import os
from io import BytesIO
from PIL import Image
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY не найден! Проверьте файл .env")

client = AsyncOpenAI(
    base_url="https://polza.ai/api/v1",
    api_key=api_key,
    timeout=60.0,
)

MODEL = "openai/gpt-5.5"

_SYSTEM_PROMPT = (
    "Ты — ИИ-модуль кулинарного приложения. Из текста или страницы по ссылке извлеки название блюда и список ингредиентов.\n\n"

    "НАЗВАНИЕ БЛЮДА:\n"
    "- Короткое и понятное: «Борщ», «Блины», «Торт Наполеон».\n"
    "- Если не можешь определить — напиши «Новый рецепт».\n\n"

    "НАЗВАНИЯ ИНГРЕДИЕНТОВ:\n"
    "- Золотая середина: «масло сливочное» ✓, «мука пшеничная» ✓ — не «масло» и не «масло 82% Экстра».\n"
    "- Убирай марки и сорта: без «ГОСТ», «экстра», «высший сорт».\n"
    "- Убирай пояснения о применении: «для смазки», «для обжарки», «на гарнир».\n"
    "- Именительный падеж, ед.число: «яйцо», «морковь».\n"
    "- Все названия на русском. «flour» → «мука», «butter» → «масло сливочное».\n\n"

    "КОЛИЧЕСТВО:\n"
    "- Число (float). При диапазоне 2–3 бери максимум (3.0).\n"
    "- Приблизительные: щепотка → 3.0 г | горсть → 15.0 г | несколько → 3.0 шт | немного → 10.0 г\n"
    "  по вкусу: соль/сахар → 5.0 г, перец/специи → 2.0 г, зелень → 10.0 г, прочее → 1.0 шт\n"
    "  жидкость без количества → 50.0 мл\n\n"

    "ЕДИНИЦЫ: строго одно из «г», «мл», «шт», «л», «ст. л.», «ч. л.\"\n\n"

    "АЛЬТЕРНАТИВЫ:\n"
    "- «сливочное или растительное масло 30 г» → добавляй ОБА с одинаковым количеством.\n"
    "- Опциональные («по желанию») и декоративные («для украшения») — включай.\n\n"

    "ЕСЛИ НЕ РЕЦЕПТ: верни {\"dish\": \"\", \"ingredients\": []}\n"
    "НЕСКОЛЬКО РЕЦЕПТОВ: бери только первый/основной.\n\n"

    "ФОРМАТ ОТВЕТА — только чистый JSON-объект, без пояснений и markdown:\n"
    "{\n"
    "  \"dish\": \"Борщ\",\n"
    "  \"ingredients\": [\n"
    "    {\"name\": \"свёкла\", \"amount\": 300.0, \"unit\": \"г\"},\n"
    "    {\"name\": \"капуста\", \"amount\": 200.0, \"unit\": \"г\"}\n"
    "  ]\n"
    "}"
)

_VISION_PROMPT = (
    "Из изображения извлеки название блюда и список ингредиентов.\n"
    "Названия переводи на русский язык.\n"
    "Приблизительные количества: щепотка → 3 г, горсть → 15 г, по вкусу (соль) → 5 г, по вкусу (перец) → 2 г.\n"
    "Единицы: «г», «мл», «шт», «л», «ст. л.», «ч. л.»\n\n"
    "Верни СТРОГО JSON-объект без пояснений:\n"
    "{\n"
    "  \"dish\": \"Название блюда\",\n"
    "  \"ingredients\": [{\"name\": \"продукт\", \"amount\": 1.0, \"unit\": \"шт\"}]\n"
    "}"
)


def _parse_llm_response(text: str) -> tuple:
    if not text:
        return "Новый рецепт", []
    text = text.strip()
    if "```" in text:
        for block in text.split("```"):
            block = block.strip().lstrip("json").strip()
            if block.startswith(("{", "[")):
                text = block
                break


    obj_start = text.find("{")
    obj_end = text.rfind("}")
    if obj_start != -1 and obj_end > obj_start:
        data = json.loads(text[obj_start:obj_end + 1])
        if isinstance(data, dict):
            dish = (data.get("dish") or "Новый рецепт").strip() or "Новый рецепт"
            return dish, data.get("ingredients", [])

    arr_start = text.find("[")
    arr_end = text.rfind("]")
    if arr_start != -1 and arr_end > arr_start:
        return "Новый рецепт", json.loads(text[arr_start:arr_end + 1])

    return "Новый рецепт", []


async def parse_ingredients_with_llm(raw_text: str, retries: int = 3) -> tuple:
    for attempt in range(retries):
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0.0,
                max_tokens=2048,
                extra_body={"plugins": [{"id": "web", "max_results": 5}]},
            )
            return _parse_llm_response(response.choices[0].message.content)

        except json.JSONDecodeError as e:
            logger.error("JSON parse error (попытка %d/%d): %s", attempt + 1, retries, e)
            if attempt == retries - 1:
                return "Новый рецепт", []

        except Exception as e:
            logger.error("LLM API error (попытка %d/%d): %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return "Новый рецепт", []

    return "Новый рецепт", []


async def parse_ingredients_from_image(image_path: str, retries: int = 3) -> tuple:
    try:
        img = Image.open(image_path).convert("RGB")
        if max(img.size) > 1920:
            img.thumbnail((1920, 1920), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        if buf.tell() > 4 * 1024 * 1024:
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=50)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
    except Exception as e:
        logger.error("Ошибка кодирования изображения: %s", e)
        return "Новый рецепт", []

    for attempt in range(retries):
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }],
                max_tokens=2048,
            )
            return _parse_llm_response(response.choices[0].message.content)

        except json.JSONDecodeError as e:
            logger.error("JSON parse error фото (попытка %d/%d): %s", attempt + 1, retries, e)
            if attempt == retries - 1:
                return "Новый рецепт", []

        except Exception as e:
            logger.error("Vision API error (попытка %d/%d): %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return "Новый рецепт", []

    return "Новый рецепт", []
