import json
from openai import AsyncOpenAI
import os
# Настраиваем клиента на сервер OpenRouter
api_key = os.environ.get("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError("Критическая ошибка: Переменная окружения OPENROUTER_API_KEY не найдена!")

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key
)

async def parse_ingredients_with_llm(raw_text: str) -> list:
    prompt = (
        "Ты — специализированный ИИ-модуль для кулинарного приложения. "
        "Твоя задача — извлечь из сырого текста рецепта список ингредиентов.\n\n"
        "Правила:\n"
        "1. Игнорируй шаги приготовления, инструкции, заголовки и мусор.\n"
        "2. Приводи названия продуктов к начальной форме (именительный падеж, единственное число, например: 'яйцо', 'масло сливочное').\n"
        "3. Если у продукта есть пояснение для чего он (например, 'для смазки сковороды'), отсекай это пояснение, оставляй только сам продукт.\n"
        "4. Количество должно быть строго числом (float). Если указан диапазон (2-3), бери максимальное значение (3.0). Если количество не указано, ставь 1.0.\n"
        "5. Единицы измерения пиши сокращенно и стандартно ('г', 'мл', 'шт', 'л', 'ст. л.', 'ч. л.').\n\n"
        "Ответ верни СТРОГО в формате JSON-массива объектов. Никакого лишнего текста, только чистый JSON.\n"
        "Пример формата:\n"
        "[\n"
        "  {\"name\": \"молоко\", \"amount\": 500.0, \"unit\": \"мл\"},\n"
        "  {\"name\": \"яйцо\", \"amount\": 3.0, \"unit\": \"шт\"}\n"
        "]"
    )

    try:
        response = await client.chat.completions.create(
            model="openrouter/auto:free", 
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": raw_text}
            ],
            temperature=0.0
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # На всякий случай очищаем ответ от возможных markdown-оберток ```json ... ```
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        data = json.loads(result_text.strip())
        
        if isinstance(data, dict):
            for key in ["ingredients", "items", "data"]:
                if key in data:
                    return data[key]
            return list(data.values())[0] if data else []
            
        return data

    except Exception as e:
        print(f"Ошибка ИИ парсера: {e}")
        return []