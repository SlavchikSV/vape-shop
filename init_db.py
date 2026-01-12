# init_db.py
import os
import sqlite3
from flask_bcrypt import Bcrypt
import subprocess

bcrypt = Bcrypt()

def restore_from_github():
    """Восстанавливает базу из последнего бэкапа в GitHub"""
    print("🔄 Проверяю наличие бэкапов в GitHub...")
    
    try:
        # Пробуем получить последние изменения из GitHub
        result = subprocess.run(['git', 'pull'], 
                              capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"⚠️ Ошибка при загрузке из GitHub: {result.stderr}")
            return False
        
        # Проверяем есть ли бэкапы
        backup_dir = 'backups'
        if os.path.exists(backup_dir):
            backups = sorted([
                f for f in os.listdir(backup_dir) 
                if f.startswith('shop_backup_') and f.endswith('.db')
            ])
            
            if backups:
                latest_backup = os.path.join(backup_dir, backups[-1])
                
                # Восстанавливаем базу
                import shutil
                shutil.copy2(latest_backup, 'shop.db')
                print(f"✅ База восстановлена из: {latest_backup}")
                return True
        
        print("⚠️ Бэкапы не найдены, создаю новую базу")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка восстановления: {e}")
        return False

def create_new_database():
    """Создает новую базу данных с продавцами"""
    print("🆕 Создаю новую базу данных...")
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    # Таблица продавцов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sellers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        role TEXT DEFAULT 'seller',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица товаров
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        cost_price REAL NOT NULL,
        sell_price REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'в наличии',
        shipment_id INTEGER,
        date_arrived TEXT,
        date_sold TEXT,
        date_taken TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица поставок
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shipment_number TEXT UNIQUE NOT NULL,
        order_date TEXT NOT NULL,
        delivery_cost REAL DEFAULT 0,
        status TEXT DEFAULT 'в пути',
        total_items INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Добавляем продавцов
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
    
    print("✅ Новая база данных создана")
    return True

def init_database():
    """Основная функция инициализации"""
    print("=" * 50)
    print("🔄 ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
    print("=" * 50)
    
    # Пробуем восстановить из GitHub
    restored = restore_from_github()
    
    # Если не удалось восстановить, создаем новую
    if not restored:
        create_new_database()
    
    print("=" * 50)
    print("✅ БАЗА ДАННЫХ ГОТОВА К РАБОТЕ")
    print("=" * 50)

if __name__ == '__main__':
    init_database()
