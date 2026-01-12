# fix_errors.py - временный фикс
import os
import sqlite3

def fix_database():
    """Создает недостающую таблицу или удаляет зависимости от неё"""
    db_path = 'shop.db'
    
    if not os.path.exists(db_path):
        print("База данных не найдена")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Пробуем создать таблицу
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL
        )
        ''')
        print("Таблица active_sessions создана или уже существует")
    except Exception as e:
        print(f"Не удалось создать таблицу: {e}")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    fix_database()
