import sys
import io
import re
import sqlite3

# 1. Заставляем терминал дружить с русским языком
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
from natasha import Segmenter, MorphVocab, NewsEmbedding, NewsMorphTagger, Doc

def clean_recipe_text(raw_text: str) -> str:
    #Отсекает инструкцию по приготовлению, оставляя только ингредиенты.
    markers = ["приготовление", "инструкция", "шаги", "способ приготовления", "как готовить", "процесс"]
    text_lower = raw_text.lower()
    for marker in markers:
        if marker in text_lower:
            marker_index = text_lower.find(marker)
            return raw_text[:marker_index].strip()
    return raw_text.strip()

def parse_ingredients_simple_ai(cleaned_text: str) -> list:
    # Инициализируем ИИ Natasha
    segmenter = Segmenter()
    morph_vocab = MorphVocab()
    emb = NewsEmbedding()
    morph_tagger = NewsMorphTagger(emb)
    
    ingredients_list = []
    #Заменяем слова на краткие формы, чтобы избежать проблемы с регулярными выражениями
    text = cleaned_text.lower()
    text = text.replace("килограмм", "кг").replace("кило", "кг")
    text = text.replace("грамм", "г").replace("гр", "г")
    text = text.replace("милилитров", "мл").replace("милилитр", "мл")
    text = text.replace("литров", "л").replace("литра", "л").replace("литр", "л")

    # Шаблон для поиска Числа и Единицы измерения в строке
    pattern = r'(\d+[\.,]?\d*)\s*(кг|мл|шт|ст\.\s*л\.|ч\.\s*л\.|зубчик|пучок|стакан|г|л)?'
    
    # Режем текст по строкам
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue # Пропускаем пустые строки
            
        # Ищем число и единицу измерения в текущей строке
        match = re.search(pattern, line.lower())
        
        if match:
            amount = float(match.group(1).replace(',', '.'))
            unit = match.group(2) if match.group(2) else "шт"
            
            # Вырезаем число и единицу из строки, остальное — это название продукта
            raw_name = re.sub(pattern, '', line.lower())
            raw_name = raw_name.replace('-', '').replace(':', '').strip()
            
            # Подключаем ИИ для работы со словами (форма слова, части речи)
            doc = Doc(raw_name)
            doc.segment(segmenter) #разбитие по токенам
            doc.tag_morph(morph_tagger) #части речи
            
            # Собираем слова, приведенные ИИ к начальной форме (лемме)
            lemma_words = []
            for token in doc.tokens:
                token.lemmatize(morph_vocab)
                # Берем только существительные и прилагательные (минусуем предлоги и мусор)
                if token.pos in ['NOUN', 'ADJ']:
                    lemma_words.append(token.lemma)
            
            # Объединяем слова обратно в красивое название
            clean_name = " ".join(lemma_words)
            
            # Если имя после чистки не пустое, добавляем в список
            if clean_name:
                ingredients_list.append({
                    "name": clean_name,
                    "amount": amount,
                    "unit": unit
                })
                
    return ingredients_list

DB_NAME = "recipes_bot.db"

def init_db():
    # Создает таблицы в базе данных, если их еще нет.
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица рецептов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recipes (
        recipe_id INTEGER PRIMARY KEY AUTOINCREMENT,    
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL
    )
    """)
    
    # Таблица ингредиентов со связью по recipe_id и каскадным удалением
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        amount REAL NOT NULL,
        unit TEXT NOT NULL,
        FOREIGN KEY (recipe_id) REFERENCES recipes (recipe_id) ON DELETE CASCADE
    )
    """)
    
    #сохраняем результат
    conn.commit()
    conn.close()

def save_recipe_to_db(user_id: int, title: str, ingredients: list) -> int:
    # Сохраняет рецепт и его ингредиенты в базу данных.
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Вставляем сам рецепт
    cursor.execute("INSERT INTO recipes (user_id, title) VALUES (?, ?)", (user_id, title))  #защита от SQL-инъекций с помощью ?
    recipe_id = cursor.lastrowid # Получаем ID только что созданного рецепта
    
    # 2. Вставляем все его продукты
    for item in ingredients:
        cursor.execute("""
        INSERT INTO ingredients (recipe_id, name, amount, unit) 
        VALUES (?, ?, ?, ?)
        """, (recipe_id, item['name'], item['amount'], item['unit']))
        
    conn.commit()
    conn.close()
    return recipe_id

def get_combined_shopping_list(recipe_ids: list) -> list:
    #Берет список ID рецептов, достает их ингредиенты из БД
    #и суммирует количества одинаковых продуктов.
    
    if not recipe_ids:
        return []
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Еще одна защита от инъекций
    # Например, если recipe_ids = [1, 2], то строка превратится в "SELECT * FROM ingredients WHERE recipe_id IN (?, ?)"
    placeholders = ",".join("?" for _ in recipe_ids)
    query = f"SELECT name, amount, unit FROM ingredients WHERE recipe_id IN ({placeholders})"
    
    cursor.execute(query, recipe_ids)
    rows = cursor.fetchall()
    conn.close()
    
    # Словарь для объединения. Ключом будет кортеж (название, единица_измерения)
    # Например: { ("куриный филе", "г"): 200 }
    combined = {}
    
    for name, amount, unit in rows:
        key = (name, unit)
        if key in combined:
            combined[key] += amount # Если такой продукт с такой ед. изм. уже есть, плюсуем
        else:
            combined[key] = amount  # Если нет, создаем новую запись
            
    # Пересобираем словарь обратно в красивый список словарей
    shopping_list = []
    for (name, unit), amount in combined.items():
        shopping_list.append({
            "name": name,
            "amount": amount,
            "unit": unit
        })
        
    return shopping_list

if __name__ == "__main__":
    print("--- ЛОКАЛЬНЫЙ ТЕСТ СИСТЕМЫ ОБЪЕДИНЕНИЯ РЕЦЕПТОВ ---")
    init_db() # Создаем таблицы, если их нет
    
    # Имитируем одного пользователя
    user_id = 777
    
    # Рецепт 1
    title_1 = "Утренний омлет"
    text_1 = "Яйца - 3 шт\nМолоко - 100 мл\nПомидоры - 1 шт"
    
    # Рецепт 2
    title_2 = "Итальянская паста"
    text_2 = "Томаты - 2 шт\nМука - 200 г\nЯйца - 2 шт"
    
    # 1. Пропускаем оба рецепта через ИИ и сохраняем в БД
    print(f"\nРазбираем: {title_1}...")
    ingr_1 = parse_ingredients_simple_ai(clean_recipe_text(text_1))
    id_1 = save_recipe_to_db(user_id, title_1, ingr_1)
    
    print(f"Разбираем: {title_2}...")
    ingr_2 = parse_ingredients_simple_ai(clean_recipe_text(text_2))
    id_2 = save_recipe_to_db(user_id, title_2, ingr_2)
    
    # 2. Тестируем калькулятор объединения (как будто пользователь выбрал оба этих блюда)    
    # Передаем список ID рецептов, которые хотим объединить
    chosen_recipes = [id_1, id_2] 
    
    # В коде ТГ-бота мы использовали встроенный кусок, давай вызовем get_combined_shopping_list
    # (Убедись, что функция get_combined_shopping_list есть у тебя в коде выше)
    shopping_list = get_combined_shopping_list(chosen_recipes)
    
    print("\n🛒 ИТОГОВЫЙ СПИСОК ПОКУПОК:")
    print("-" * 30)
    for item in shopping_list:
        print(f"• {item['name'].capitalize()} — {item['amount']} {item['unit']}")
    print("-" * 30)