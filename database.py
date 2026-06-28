import sqlite3

DB_NAME = "pantry.db"

def init_db():
    # Создает таблицы в базе данных, если их еще нет
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    ''')
    
    # Таблица ингредиентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            amount REAL,
            unit TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str):
    # Регистрирует пользователя в базе
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username, first_name)
    )
    conn.commit()
    conn.close()

def save_ingredients(user_id: int, items: list):
    # Сохраняет список распарсенных ингредиентов в базу
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    for item in items:
        name = item.get('name', '').lower().strip()
        amount = item.get('amount', 1.0)
        unit = item.get('unit', 'шт').lower().strip()
        
        if name:
            cursor.execute(
                "INSERT INTO ingredients (user_id, name, amount, unit) VALUES (?, ?, ?, ?)",
                (user_id, name, amount, unit)
            )
            
    conn.commit()
    conn.close()

def get_aggregated_ingredients(user_id: int) -> list:
    # Группирует продукты с одинаковым именем и одинаковой единицей измерения
    # и суммирует их количество (amount)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT name, SUM(amount), unit 
        FROM ingredients 
        WHERE user_id = ? 
        GROUP BY name, unit
        ORDER BY name ASC
    ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Превращаем результат в удобный список словарей
    result = []
    for row in rows:
        result.append({
            'name': row[0],
            'amount': row[1],
            'unit': row[2]
        })
    return result

def clear_user_products(user_id: int):
    # Очищает список покупок пользователя
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ingredients WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()