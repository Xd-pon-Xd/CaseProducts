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


if __name__ == "__main__":
    init_db()
    
    # Тестовый рецепт, как будто его прислал пользователь с Telegram ID: 12345
    test_user_id = 12345
    test_title = "Борщ"
    test_text = "Говядина - 500грамм\nвзять Картошку - 3 шт\nвместо Свеклы - 2 шт"
    
    # Парсим рецепт
    parsed_ingredients = parse_ingredients_simple_ai(test_text)
    
    # Сохраняем в бд
    r_id = save_recipe_to_db(test_user_id, test_title, parsed_ingredients)
        
    # Прочитаем данные из файла бд для проверки
    connection = sqlite3.connect(DB_NAME)
    cur = connection.cursor()
    cur.execute("SELECT * FROM recipes")
    print(cur.fetchall())
    cur.execute("SELECT * FROM ingredients")
    print(cur.fetchall())
    connection.close()