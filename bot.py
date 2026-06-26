import sys
import io
import re

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
            doc.segment(segmenter)
            doc.tag_morph(morph_tagger)
            
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

if __name__ == "__main__":
    # Наш самый первый, классический пример в столбик, где всё гарантированно должно работать
    test_recipe = """
    Салат Цезарь.
    Ингредиенты:
    возьмем 200г куриного филе, запечем
    Свежие помидоры - 2 шт
    Сыр Пармезан - 50г
    
    Приготовление:
    1. Нарезать филе...
    """
    
    only_ingredients = clean_recipe_text(test_recipe)
    parsed_data = parse_ingredients_simple_ai(only_ingredients)
    
    for item in parsed_data:
        print(f"Продукт: {item['name']} | Кол-во: {item['amount']} | Ед: {item['unit']}")