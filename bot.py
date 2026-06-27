import sys
import io
import re
import sqlite3
import datetime
from natasha import Segmenter, MorphVocab, NewsEmbedding, NewsMorphTagger, Doc

# Заставляем терминал дружить с русским языком
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def clean_recipe_text(raw_text: str) -> str:
    markers = ["приготовление", "инструкция", "шаги", "способ приготовления", "как готовить", "процесс", "шаг 1"]
    text_lower = raw_text.lower()
    for marker in markers:
        if marker in text_lower:
            return raw_text[:text_lower.find(marker)].strip()
    return raw_text.strip()

def extract_recipe_title(raw_text: str) -> str:
    # Умный анализ текста для извлечения названия рецепта.
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    if not lines:
        return "Новый рецепт"
        
    first_line = lines[0]
    
    # 1. Проверка на слишком длинную строку (название не должно быть целым абзацем)
    if len(first_line) > 40:
        return f"Рецепт {datetime.date.today().strftime('%d.%m.%Y')}"
        
    # 2. Проверка: если в первой строке уже есть цифры и единицы измерения,
    # значит пользователь забыл название и сразу начал с ингредиентов.
    pattern_has_ingredients = r'\d+\s*(кг|мл|шт|г|гр|литр|ложка|ст|ч)'
    if re.search(pattern_has_ingredients, first_line.lower()):
        # Названия нет, возвращаем дефолтное с датой
        return f"Рецепт {datetime.date.today().strftime('%d.%m.%Y')}"
        
    # 3. Если строчка чистая, убираем из неё лишние знаки препинания в конце (если есть)
    clean_title = first_line.rstrip('.:!,- ')
    
    return clean_title.capitalize()

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
    print("--- ТЕСТ УМНОГО ОПРЕДЕЛЕНИЯ НАЗВАНИЙ ---")
    
    # Случай 1: Написал как надо
    text_perfect = "Итальянская пицца\nТесто - 200г\nСыр - 100г"
    
    # Случай 2: Забыл название, написал сразу продукты
    text_lazy = "500г курицы\n3 шт картошки"
    
    # Случай 3: Пользователь написал слишком длинную строку вместо названия
    text_long = "Я вчера готовил суп, ну он в целом норм, так что сделаем:\nВода - 2 л\nМясо - 300 г"

    print(f"Текст 1 -> Определено название: '{extract_recipe_title(text_perfect)}'")
    print(f"Текст 2 -> Определено название: '{extract_recipe_title(text_lazy)}'")
    print(f"Текст 3 -> Определено название: '{extract_recipe_title(text_long)}'")