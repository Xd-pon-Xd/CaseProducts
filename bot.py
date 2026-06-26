import sys
import io
import re

# 1. Заставляем терминал дружить с русским языком
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def clean_recipe_text(raw_text: str) -> str:
    # Функция проходит по тексту и ищет ключевые слова - граница между ингредиентами и способом приготовления, чтобы избежать дублирования
    markers = ["приготовление", "инструкция", "шаги", "способ приготовления", "как готовить", "процесс", "пошаговый"]
    text_lower = raw_text.lower()
    for marker in markers:
        if marker in text_lower:
            marker_index = text_lower.find(marker)
            return raw_text[:marker_index].strip()
    return raw_text.strip()

def parse_ingredients(cleaned_text: str) -> list:
    #Разбирает текст ингредиентов по строкам и извлекает:
    #название продукта, количество и единицу измерения.
    ingredients_list = []
    
    # Разбиваем текст на отдельные строчки
    lines = cleaned_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue # Пропускаем пустые строки
            
        # Регулярное выражение для поиска чисел и единиц измерения (г, кг, мл, шт, ст. л. и т.д.)
        # Ищет шаблоны вида: "200г", "1.5 кг", "2 шт", "5 ст. л."
        pattern = r'(\d+[\.,]?\d*)\s*(г|кг|мл|л|шт|ст\.\s*л\.|ч\.\s*л\.|зубчик|пучок|стакан|гр|килограмм)?'
        
        match = re.search(pattern, line.lower())
        
        if match:
            amount = float(match.group(1).replace(',', '.')) # Превращаем строку "1,5" в число 1.5
            unit = match.group(2) if match.group(2) else "шт" # Если единица не найдена, пусть будет "шт"
            
            # Название продукта — это всё, что осталось в строке, очищенное от цифр и единиц
            name = re.sub(pattern, '', line.lower())
            # Убираем лишние знаки препинания (тире, двоеточия, пробелы)
            name = name.replace('-', '').replace(':', '').strip()
            
            ingredients_list.append({
                "name": name,
                "amount": amount,
                "unit": unit
            })
            
    return ingredients_list

if __name__ == "__main__":
    # Тестируем связку двух функций
    test_recipe = """
    Салат Цезарь.
    Ингредиенты:
    Куриное филе - 200г
    Салат Романо - 1 пучок
    Сыр Пармезан - 50 г
    Яйца - 2 шт
    Помидоры черри - 1.5 килограмм
    
    Приготовление:
    1. Обжарить филе...
    """
    
    print("1. Отрезаем инструкцию...")
    only_ingredients = clean_recipe_text(test_recipe)
    
    print("2. Парсим ингредиенты в структуру...")
    parsed_data = parse_ingredients(only_ingredients)
    
    # Красиво выводим результат
    for item in parsed_data:
        print(f"{item['name']}: {item['amount']} {item['unit']}")
