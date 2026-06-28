import sqlite3

DB_NAME = "pantry.db"

# Справочник базового перевода в единую систему (всё переводим в граммы и миллилитры)
# Это нужно, чтобы внутри базы складывать 1 кг и 500 г
UNIT_CONVERSION = {
    # Вес (базовая единица - грамм)
    'г': {'base': 'г', 'factor': 1.0},
    'грамм': {'base': 'г', 'factor': 1.0},
    'кг': {'base': 'г', 'factor': 1000.0},
    'килограмм': {'base': 'г', 'factor': 1000.0},
    'ст. л.': {'base': 'г', 'factor': 15.0},      # Средняя ст. ложка сыпучих/жидких ~15г
    'ч. л.': {'base': 'г', 'factor': 5.0},        # Чайная ложка ~5г
    'щепотка': {'base': 'г', 'factor': 1.0},      # Щепотка ~ 1г
    
    # Объем (базовая единица - мл)
    'мл': {'base': 'мл', 'factor': 1.0},
    'миллилитр': {'base': 'мл', 'factor': 1.0},
    'л': {'base': 'мл', 'factor': 1000.0},
    'литр': {'base': 'мл', 'factor': 1000.0},
    'стакан': {'base': 'мл', 'factor': 200.0},    # Стандартный стакан - 200мл
}

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    ''')
    
    # ДОБАВИЛИ КОРРЕКТНУЮ СТРУКТУРУ С RECIPE_NAME
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            recipe_name TEXT,
            name TEXT,
            amount REAL,
            unit TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, username, first_name))
    conn.commit()
    conn.close()

# ТЕПЕРЬ ПРИНИМАЕМ НАЗВАНИЕ РЕЦЕПТА
def save_ingredients(user_id: int, recipe_name: str, items: list):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    for item in items:
        name = item.get('name', '').lower().strip()
        amount = item.get('amount', 1.0)
        unit = item.get('unit', 'шт').lower().strip()
        
        if name:
            cursor.execute(
                "INSERT INTO ingredients (user_id, recipe_name, name, amount, unit) VALUES (?, ?, ?, ?, ?)",
                (user_id, recipe_name, name, amount, unit)
            )
            
    conn.commit()
    conn.close()

def get_user_recipes(user_id: int) -> list:
    """Возвращает список всех уникальных названий блюд пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT recipe_name FROM ingredients WHERE user_id = ?", (user_id,))
    recipes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return recipes

def get_aggregated_ingredients(user_id: int) -> list:
    # Агрегация с переводом весов
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Извлекаем вообще все продукты юзера для ручной умной группировки
    cursor.execute("SELECT name, amount, unit FROM ingredients WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    totals = {}
    
    for name, amount, unit in rows:
        unit = unit.lower().strip()
        name = name.lower().strip()
        
        if name not in totals:
            totals[name] = {'г': 0.0, 'мл': 0.0, 'шт': 0.0}
            
        # Проверяем, умеем ли мы конвертировать эту единицу
        if unit in UNIT_CONVERSION:
            base_unit = UNIT_CONVERSION[unit]['base']
            factor = UNIT_CONVERSION[unit]['factor']
            # Переводим в базовую единицу (г или мл) и прибавляем
            totals[name][base_unit] += amount * factor
        else:
            totals[name]['шт'] += amount

    # Формируем красивый итоговый список с обратным переводом для гигантских чисел
    result = []
    for name, measures in totals.items():
        # 1. Обрабатываем весовые (граммы)
        if measures['г'] > 0:
            final_amount = measures['г']
            final_unit = 'г'
            if final_amount >= 1000: # Если больше 1000г, переводим обратно в кг для красоты
                final_amount /= 1000.0
                final_unit = 'кг'
            result.append({'name': name, 'amount': final_amount, 'unit': final_unit})
            
        # 2. Обрабатываем объемные (миллилитры)
        if measures['мл'] > 0:
            final_amount = measures['мл']
            final_unit = 'мл'
            if final_amount >= 1000: # Если больше 1000мл, переводим в литры
                final_amount /= 1000.0
                final_unit = 'л'
            result.append({'name': name, 'amount': final_amount, 'unit': final_unit})
            
        # 3. Обрабатываем штучные
        if measures['шт'] > 0:
            result.append({'name': name, 'amount': measures['шт'], 'unit': 'шт'})
            
    return result

def clear_user_products(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ingredients WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()