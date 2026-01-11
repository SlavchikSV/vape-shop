[file name]: update_db.py
[file content begin]
#!/usr/bin/env python3
"""
Скрипт для обновления базы данных
Запустите: python update_db.py
"""

import sqlite3
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()

def update_database():
    """Обновить структуру базы данных"""
    
    print("🔧 Обновление базы данных...")
    
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Проверяем существование таблицы shipments
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shipments';")
        if not cursor.fetchone():
            print("📦 Создаю таблицу поставок...")
            cursor.execute('''
            CREATE TABLE shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shipment_number TEXT UNIQUE NOT NULL,
                order_date TEXT NOT NULL,
                received_date TEXT,
                delivery_cost REAL DEFAULT 0,
                status TEXT DEFAULT 'в пути',
                total_items INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
        
        # Проверяем существование столбца manual_price в items
        cursor.execute("PRAGMA table_info(items);")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'manual_price' not in columns:
            print("💰 Добавляю столбец manual_price...")
            cursor.execute('ALTER TABLE items ADD COLUMN manual_price REAL')
        
        if 'shipment_id' not in columns:
            print("📦 Добавляю столбец shipment_id...")
            cursor.execute('ALTER TABLE items ADD COLUMN shipment_id INTEGER')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_shipment ON items(shipment_id)')
        
        if 'date_reserved' not in columns:
            print("⏰ Добавляю столбец date_reserved...")
            cursor.execute('ALTER TABLE items ADD COLUMN date_reserved TEXT')
        
        # Проверяем столбец shipment_id в transactions
        cursor.execute("PRAGMA table_info(transactions);")
        trans_columns = [col[1] for col in cursor.fetchall()]
        
        if 'shipment_id' not in trans_columns:
            print("📦 Добавляю столбец shipment_id в transactions...")
            cursor.execute('ALTER TABLE transactions ADD COLUMN shipment_id INTEGER')
        
        # Проверяем существование таблицы sellers
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sellers';")
        if not cursor.fetchone():
            print("👥 Создаю таблицу продавцов...")
            cursor.execute('''
            CREATE TABLE sellers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                role TEXT DEFAULT 'seller',
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
            ''')
            
            # Добавляем стандартных продавцов
            default_sellers = [
                ('SlavchikSV', 'sv280606', 'Администратор', 'admin'),
                ('mkozlov', '020988mama', 'Главный администратор', 'admin'),
                ('g_nix', 'IHHujhg655G', 'Продавец G_Nix', 'seller'),
            ]
            
            for username, password, display, role in default_sellers:
                password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
                cursor.execute('''
                INSERT OR IGNORE INTO sellers (username, password_hash, display_name, role)
                VALUES (?, ?, ?, ?)
                ''', (username, password_hash, display, role))
        
        conn.commit()
        print("✅ База данных успешно обновлена!")
        
        print("\n📊 Текущая структура базы данных:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table['name']}")
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении базы данных: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    update_database()
[file content end]
