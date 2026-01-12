# init_db.py
import sqlite3
from flask_bcrypt import Bcrypt
import os

bcrypt = Bcrypt()

def init_database():
    """Инициализация базы данных с проверкой"""
    print("🔄 Инициализация базы данных...")
    
    # Проверяем, есть ли уже база в постоянном хранилище
    if os.path.exists('/data/shop.db'):
        print("📁 Копирую базу из постоянного хранилища...")
        # Копируем из постоянного хранилища в текущую директорию
        import shutil
        shutil.copy2('/data/shop.db', 'shop.db')
    
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Таблица товаров
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        cost_price REAL NOT NULL,
        sell_price REAL NOT NULL,
        status TEXT NOT NULL,
        shipment_id INTEGER,
        date_arrived TEXT,
        date_sold TEXT,
        date_taken TEXT,
        date_reserved TEXT,
        manual_price REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица транзакций
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        item_id INTEGER,
        shipment_id INTEGER,
        amount REAL,
        note TEXT
    )
    ''')
    
    # Таблица продавцов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sellers (
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
    
    # Таблица действий
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS action_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        action_type TEXT NOT NULL,
        item_id INTEGER,
        details TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица активных сессий
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS active_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        session_token TEXT UNIQUE NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT 1
    )
    ''')
    
    # Таблица уведомлений
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        from_seller_id INTEGER,
        message TEXT NOT NULL,
        item_id INTEGER,
        action_type TEXT,
        is_read BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица поставок
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS shipments (
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
    
    # Добавляем продавцов если их нет
    default_sellers = [
        ('SlavchikSV', 'sv280606', 'Администратор', 'admin'),
        ('mkozlov', '020988mama', 'Главный администратор', 'admin'),
        ('g_nix', 'IHHujhg655G', 'Продавец G_Nix', 'seller'),
    ]
    
    for username, password, display, role in default_sellers:
        cursor.execute('SELECT id FROM sellers WHERE username = ?', (username,))
        if not cursor.fetchone():
            password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            cursor.execute('''
            INSERT INTO sellers (username, password_hash, display_name, role)
            VALUES (?, ?, ?, ?)
            ''', (username, password_hash, display, role))
            print(f"✅ Добавлен продавец: {username}")
    
    conn.commit()
    conn.close()
    
    print("✅ База данных инициализирована!")
    
    # Сохраняем копию в постоянное хранилище
    if os.path.exists('shop.db'):
        try:
            if not os.path.exists('/data'):
                os.makedirs('/data', exist_ok=True)
            import shutil
            shutil.copy2('shop.db', '/data/shop.db')
            print("💾 Копия базы сохранена в постоянное хранилище")
        except Exception as e:
            print(f"⚠️ Не удалось сохранить копию: {e}")

if __name__ == '__main__':
    init_database()
