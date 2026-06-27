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

def parse_ingredients_advanced(raw_text: str) -> list:
    segmenter = Segmenter()
    morph_vocab = MorphVocab()
    emb = NewsEmbedding()
    morph_tagger = NewsMorphTagger(emb)
    
    # Блок замен
    text = raw_text.lower()
    text = text.replace("килограмм", "кг").replace("кило", "кг")
    text = text.replace("грамм", "г").replace("гр", "г")
    text = text.replace("миллилитров", "мл").replace("миллилитр", "мл").replace("милилитр", "мл")
    text = text.replace("литров", "л").replace("литра", "л").replace("литр", "л")
    
    text = text.replace("столовая ложка", "л").replace("столовые ложки", "л").replace("ст. ложки", "л").replace("ст. л.", "л").replace("ст.л.", "л")
    text = text.replace("чайная ложка", "л").replace("чайные ложки", "л").replace("ч. ложки", "л").replace("ч. л.", "л").replace("ч.л.", "л")
    text = text.replace("ложки", "л").replace("ложка", "л").replace("ложку", "л")
    
    # Убираем знаки препинания, чтобы не мешать стыковке слов
    text = re.sub(r'(?<!\d)[,;\\.](?!\d)', ' ', text)
    text = re.sub(r'\s+', ' ', text) # Удаляем лишние пробелы
    
    units_pattern = r'(кг|мл|шт|г|л)'
    
    # --- УМНОЕ УДАЛЕНИЕ ДУБЛИРУЮЩИХ СКОБОК ЛЮБОЙ ДЛИНЫ ---
    # Находим единицу измерения, после которой идет любая скобка, содержащая внутри хотя бы одну цифру
    # Это сотрет и "(2 л)", и "(около 1,5 стакана ёмкостью 200 мл)"
    text = re.sub(r'\b' + units_pattern + r'\b\s*\([^)]*\d+[^)]*\)', r'\1', text)
    
    ingredients_list = []
    
    while True:
        # Ищем паттерн количества: цифра (целая или дробная) + ед. измерения
        match = re.search(r'\(?(\d+[\d\.,\-/]*)\s*' + units_pattern + r'?\)?', text)
        if not match:
            break
            
        raw_amount = match.group(1)
        unit = match.group(2) if match.group(2) else "шт"
        
        num_start, num_end = match.start(), match.end()
        left_part = text[:num_start].strip()
        right_part = text[num_end:].strip()
        
        # Очищаем левую часть от тире, двоеточия на концах слов
        left_part_clean = re.sub(r'[:\-=\s]+$', '', left_part).strip()
        left_words = left_part_clean.split()
        right_words = right_part.split()
        
        product_name = ""
        
        # --- ПРОСМОТР СЛЕВА ---
        if left_words:
            # Пропускаем текстовые скобки типа "(или растительное)", если они остались
            if left_words[-1].endswith(')'):
                left_str = " ".join(left_words)
                open_bracket_idx = left_str.rfind('(')
                if open_bracket_idx != -1:
                    left_words = left_str[:open_bracket_idx].strip().split()
            
            # Фильтруем левые слова от тире и знаков препинания
            left_words = [w for w in left_words if w not in ['-', '—', '–', ':', '=']]
            
            if left_words:
                words_to_analyze = left_words[-2:] if len(left_words) >= 2 else [left_words[-1]]
                # Убираем возможные тире из самих слов
                words_to_analyze = [w.replace('-', '').replace('—', '') for w in words_to_analyze]
                candidate_raw = " ".join(words_to_analyze).strip()
                
                doc = Doc(candidate_raw)
                doc.segment(segmenter)
                doc.tag_morph(morph_tagger)
                pos_tags = [t.pos for t in doc.tokens]
                
                if len(pos_tags) == 2 and pos_tags[0] == 'NOUN' and pos_tags[1] == 'NOUN':
                    product_name = words_to_analyze[-1]
                else:
                    product_name = candidate_raw
                    
                # Вырезаем найденный продукт из текста
                pos = left_part.rfind(product_name)
                if pos != -1:
                    text = left_part[:pos].strip() + " " + right_part
                else:
                    text = left_part_clean[:-len(product_name)].strip() + " " + right_part
                    
        # --- ПРОСМОТР СПРАВА ---
        if not product_name and right_words:
            # Очищаем правые слова от мусора
            right_words = [w for w in right_words if w not in ['-', '—', '–', ':', '=']]
            if right_words:
                words_to_analyze = right_words[:2] if len(right_words) >= 2 else [right_words[0]]
                candidate_raw = " ".join(words_to_analyze).replace('(', '').replace(')', '').replace('-', '')
                
                doc = Doc(candidate_raw)
                doc.segment(segmenter)
                doc.tag_morph(morph_tagger)
                pos_tags = [t.pos for t in doc.tokens]
                
                if len(pos_tags) == 2 and pos_tags[0] == 'NOUN' and pos_tags[1] == 'NOUN':
                    product_name = words_to_analyze[0]
                else:
                    product_name = candidate_raw
                    
                pos = right_part.find(words_to_analyze[0])
                if pos != -1:
                    text = left_part + " " + right_part[pos + len(product_name):].strip()
                else:
                    text = left_part + " " + right_part
                    
        # Математика количества (парсинг дробей)
        try:
            if '-' in raw_amount: raw_amount = raw_amount.split('-')[-1]
            if '/' in raw_amount:
                num, denom = raw_amount.split('/')
                amount = float(num) / float(denom)
            else:
                amount = float(raw_amount.replace(',', '.'))
        except:
            amount = 1.0
            
        # Лемматизация названия продукта через ИИ Natasha
        if product_name:
            product_name = re.sub(r'[:\-=\(\)]', '', product_name).strip()
            doc = Doc(product_name)
            doc.segment(segmenter)
            doc.tag_morph(morph_tagger)
            
            lemma_words = []
            for token in doc.tokens:
                token.lemmatize(morph_vocab)
                if token.pos in ['NOUN', 'ADJ']:
                    lemma_words.append(token.lemma)
                    
            clean_name = " ".join(lemma_words)
            if clean_name and clean_name not in ['продукты']: # Отсекаем заголовок секции, если он попался
                ingredients_list.append({"name": clean_name, "amount": amount, "unit": unit})
                
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
    print("--- ТЕСТ СУЩЕСТВИТЕЛЬНЫХ ---")
    
    test_1 = "3 яйца, мука 200 г, масло сливочное 30 г, морковь (2шт), капуста(3шт)"
    test_2 = "молоко 500мл  яйца 3 шт.  мука 0.5 г масло сливочное (или растительное) 30 г (3 ст. ложки) сахар 30 г (2 ст. ложки) соль 2-3 г (1/2 ч. ложки)"
    test_3 = "Продукты Молоко - 400 мл Вода - 100 мл Яйца - 2 шт. Масло растительное - 30 мл (2 ст. ложки) Мука - 200 г (около 1,5 стакана ёмкостью 200 мл) Сахар - 2 ст. ложки Соль - 0,25 ч. ложки Масло сливочное для смазывания блинов - 50 г"
    
    print("\nТест 1 (Прилагательное + Существительное):")
    for item in parse_ingredients_advanced(test_1):
        print(f"• {item['name'].capitalize()} — {item['amount']} {item['unit']}")
        
    print("\nТест 2 (Два существительных подряд влево):")
    for item in parse_ingredients_advanced(test_2):
        print(f"• {item['name'].capitalize()} — {item['amount']} {item['unit']}")

    print("\nТест 3 (Два существительных подряд вправо):")
    for item in parse_ingredients_advanced(test_3):
        print(f"• {item['name'].capitalize()} — {item['amount']} {item['unit']}")