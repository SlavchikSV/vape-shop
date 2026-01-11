[file name]: app.py
[file content begin]
import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash
from flask_bcrypt import Bcrypt
import sqlite3
from datetime import datetime, timedelta
import secrets
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'ваш-секретный-ключ-измените-это'
bcrypt = Bcrypt(app)

# ==================== БАЗА ДАННЫХ ====================
def get_db():
    """Подключение к базе данных"""
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных (основные таблицы)"""
    conn = get_db()
    
    # Таблица товаров
    conn.execute('''
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица транзакций
    conn.execute('''
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
    conn.execute('''
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
    conn.execute('''
    CREATE TABLE IF NOT EXISTS action_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        action_type TEXT NOT NULL,
        item_id INTEGER,
        details TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_id) REFERENCES sellers (id)
    )
    ''')
    
    # Таблица активных сессий
    conn.execute('''
    CREATE TABLE IF NOT EXISTS active_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        session_token TEXT UNIQUE NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT 1,
        FOREIGN KEY (seller_id) REFERENCES sellers (id)
    )
    ''')
    
    # Таблица уведомлений
    conn.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        from_seller_id INTEGER,
        message TEXT NOT NULL,
        item_id INTEGER,
        action_type TEXT,
        is_read BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_id) REFERENCES sellers (id),
        FOREIGN KEY (from_seller_id) REFERENCES sellers (id),
        FOREIGN KEY (item_id) REFERENCES items (id)
    )
    ''')
    
    # Таблица поставок
    conn.execute('''
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
    
    # Добавляем продавцов
    try:
        default_sellers = [
            ('SlavchikSV', 'sv280606', 'Администратор', 'admin'),
            ('mkozlov', '020988mama', 'Главный администратор', 'admin'),
            ('g_nix', 'IHHujhg655G', 'Продавец G_Nix', 'seller'),
        ]
        
        for username, password, display, role in default_sellers:
            # Проверяем, существует ли уже продавец
            existing = conn.execute('SELECT id FROM sellers WHERE username = ?', (username,)).fetchone()
            if not existing:
                password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
                conn.execute('''
                INSERT INTO sellers (username, password_hash, display_name, role)
                VALUES (?, ?, ?, ?)
                ''', (username, password_hash, display, role))
        
        print("✅ Созданы продавцы: SlavchikSV, mkozlov и g_nix")
    except Exception as e:
        print(f"⚠️ Ошибка при создании продавцов: {e}")
    
    conn.commit()
    conn.close()

def update_database_structure():
    """
    Обновить структуру базы данных (добавить новые таблицы и столбцы)
    Эта функция запускается при каждом старте приложения
    """
    print("🔍 Проверка и обновление структуры базы данных...")
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 1. Таблица поставок (shipments)
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
            print("✅ Таблица shipments создана")
        else:
            print("✅ Таблица shipments уже существует")
        
        # 2. Проверяем существующие столбцы в items
        cursor.execute("PRAGMA table_info(items);")
        columns_info = cursor.fetchall()
        existing_columns = [col[1] for col in columns_info]
        
        # 3. Добавляем manual_price если его нет
        if 'manual_price' not in existing_columns:
            print("💰 Добавляю столбец manual_price в items...")
            try:
                cursor.execute('ALTER TABLE items ADD COLUMN manual_price REAL')
                print("✅ Столбец manual_price добавлен")
            except Exception as e:
                print(f"⚠️ Ошибка добавления manual_price: {e}")
        else:
            print("✅ Столбец manual_price уже существует")
        
        # 4. Добавляем shipment_id если его нет
        if 'shipment_id' not in existing_columns:
            print("📦 Добавляю столбец shipment_id в items...")
            try:
                cursor.execute('ALTER TABLE items ADD COLUMN shipment_id INTEGER')
                print("✅ Столбец shipment_id добавлен")
            except Exception as e:
                print(f"⚠️ Ошибка добавления shipment_id: {e}")
        else:
            print("✅ Столбец shipment_id уже существует")
        
        # 5. Добавляем date_reserved если его нет
        if 'date_reserved' not in existing_columns:
            print("⏰ Добавляю столбец date_reserved в items...")
            try:
                cursor.execute('ALTER TABLE items ADD COLUMN date_reserved TEXT')
                print("✅ Столбец date_reserved добавлен")
            except Exception as e:
                print(f"⚠️ Ошибка добавления date_reserved: {e}")
        else:
            print("✅ Столбец date_reserved уже существует")
        
        # 6. Добавляем shipment_id в transactions если его нет
        cursor.execute("PRAGMA table_info(transactions);")
        trans_columns = [col[1] for col in cursor.fetchall()]
        
        if 'shipment_id' not in trans_columns:
            print("📦 Добавляю столбец shipment_id в transactions...")
            try:
                cursor.execute('ALTER TABLE transactions ADD COLUMN shipment_id INTEGER')
                print("✅ Столбец shipment_id добавлен в transactions")
            except Exception as e:
                print(f"⚠️ Ошибка добавления shipment_id в transactions: {e}")
        
        # 7. Создаем индексы для ускорения поиска
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_shipment ON items(shipment_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_status ON items(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status)')
            print("✅ Индексы созданы/проверены")
        except Exception as e:
            print(f"⚠️ Ошибка создания индексов: {e}")
        
        conn.commit()
        
        # Показываем итоговую структуру
        print("\n📊 Итоговая структура базы данных:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table['name']}")
        
        print("🎉 Структура базы данных проверена и обновлена!")
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении структуры БД: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        conn.close()

def ensure_database_exists():
    """Убедиться что база данных и таблицы существуют"""
    try:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        
        # Проверяем есть ли таблица items
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items';")
        if not cursor.fetchone():
            print("🔄 Создаю основные таблицы базы данных...")
            init_db()
        else:
            print("✅ Основные таблицы уже существуют")
        
        conn.close()
        
        # Всегда проверяем и обновляем структуру
        update_database_structure()
        
    except Exception as e:
        print(f"❌ Ошибка проверки БД: {e}")
        # Создаем БД заново
        init_db()
        update_database_structure()

# Вызови эту функцию ПРИ СТАРТЕ ПРИЛОЖЕНИЯ
ensure_database_exists()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_seller_by_username(username):
    """Найти продавца по логину"""
    conn = get_db()
    seller = conn.execute('SELECT * FROM sellers WHERE username = ?', (username,)).fetchone()
    conn.close()
    return dict(seller) if seller else None

def get_seller_by_id(seller_id):
    """Найти продавца по ID"""
    conn = get_db()
    seller = conn.execute('SELECT * FROM sellers WHERE id = ?', (seller_id,)).fetchone()
    conn.close()
    return dict(seller) if seller else None

def utc_to_local(utc_dt, format_only_time=False):
    """Конвертировать UTC время в локальное (UTC+3 для Минска)"""
    if not utc_dt:
        return ""
    
    try:
        if isinstance(utc_dt, str):
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%H:%M:%S',
                '%Y-%m-%d'
            ]
            
            parsed_dt = None
            for fmt in formats:
                try:
                    parsed_dt = datetime.strptime(utc_dt, fmt)
                    break
                except:
                    continue
            
            if parsed_dt is None:
                return utc_dt
            
            utc_dt = parsed_dt
        
        # Добавляем 3 часа для Минска (UTC+3)
        local_dt = utc_dt + timedelta(hours=3)
        
        if format_only_time:
            return local_dt.strftime('%H:%M')
        else:
            return local_dt.strftime('%H:%M:%S')
            
    except Exception as e:
        print(f"Ошибка конвертации времени {utc_dt}: {e}")
        if isinstance(utc_dt, str) and len(utc_dt) > 10:
            return utc_dt[11:16]
        return str(utc_dt)

def log_action(seller_id, action_type, item_id=None, details="", ip_address=None):
    """Записать действие в лог"""
    try:
        conn = get_db()
        
        created_at_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute('''
        INSERT INTO action_log (seller_id, action_type, item_id, details, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (seller_id, action_type, item_id, details, ip_address or request.remote_addr, created_at_utc))
        
        seller = conn.execute('SELECT username, display_name FROM sellers WHERE id = ?', 
                             (seller_id,)).fetchone()
        
        seller_name = seller['display_name'] or seller['username']
        
        if action_type == 'logout':
            conn.execute('DELETE FROM notifications WHERE seller_id = ?', (seller_id,))
            print(f"🗑️ Удалены все уведомления для продавца {seller_name}")
        elif action_type != 'login':
            active_sellers = conn.execute('''
                SELECT DISTINCT seller_id FROM active_sessions 
                WHERE seller_id != ? AND is_active = 1
            ''', (seller_id,)).fetchall()
            
            action_messages = {
                'add_item': 'добавил новый товар',
                'update_item': 'изменил статус товара',
                'sale': 'продал товар',
                'purchase': 'купил товар для магазина',
                'personal': 'взял товар себе',
                'error': 'ошибка',
                'add_shipment': 'добавил поставку',
                'update_shipment': 'изменил поставку'
            }
            
            action_msg = action_messages.get(action_type, action_type)
            
            message = f"{seller_name} {action_msg}"
            
            if item_id and details:
                item = conn.execute('SELECT name FROM items WHERE id = ?', (item_id,)).fetchone()
                if item:
                    message += f": {item['name']}"
                else:
                    message += f": {details[:50]}"
            elif details:
                message += f": {details[:50]}"
            
            for active_seller in active_sellers:
                receiver_active = conn.execute('''
                    SELECT 1 FROM active_sessions 
                    WHERE seller_id = ? AND is_active = 1
                ''', (active_seller['seller_id'],)).fetchone()
                
                if receiver_active:
                    conn.execute('''
                    INSERT INTO notifications (seller_id, from_seller_id, message, item_id, action_type)
                    VALUES (?, ?, ?, ?, ?)
                    ''', (active_seller['seller_id'], seller_id, message, item_id, action_type))
        
        conn.commit()
        print(f"📝 Действие записано: {seller_id} - {action_type}")
        
    except Exception as e:
        print(f"❌ Ошибка при записи лога: {e}")
    finally:
        conn.close()

def get_recent_actions(limit=10):
    """Получить последние действия с правильным временем"""
    conn = get_db()
    
    actions = conn.execute('''
        SELECT al.*, s.username, s.display_name
        FROM action_log al
        LEFT JOIN sellers s ON al.seller_id = s.id
        ORDER BY al.created_at DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    
    conn.close()
    
    actions_list = []
    for action in actions:
        action_dict = dict(action)
        
        if action_dict['created_at']:
            try:
                created_str = str(action_dict['created_at'])
                
                if ' ' in created_str:
                    try:
                        utc_time = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        try:
                            utc_time = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S.%f')
                        except:
                            utc_time = None
                
                if utc_time:
                    local_time = utc_time + timedelta(hours=3)
                    action_dict['created_at_local'] = local_time.strftime('%d.%m.%Y %H:%M:%S')
                else:
                    action_dict['created_at_local'] = created_str
            except Exception as e:
                print(f"Ошибка конвертации времени {action_dict['created_at']}: {e}")
                action_dict['created_at_local'] = str(action_dict['created_at'])
        else:
            action_dict['created_at_local'] = ''
        
        actions_list.append(action_dict)
    
    return actions_list

def clear_old_sessions():
    """Очистка старых неактивных сессий"""
    conn = get_db()
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='active_sessions';")
        if cursor.fetchone():
            conn.execute('''
            DELETE FROM active_sessions 
            WHERE datetime(last_activity) < datetime('now', '-8 hours')
            ''')
            conn.commit()
            deleted = conn.total_changes
            if deleted > 0:
                print(f"🧹 Очищено {deleted} старых сессий")
    except Exception as e:
        print(f"Ошибка при очистке сессий: {e}")
    finally:
        conn.close()

def get_active_sellers():
    """Получить список активных продавцов"""
    conn = get_db()
    sellers = conn.execute('''
        SELECT s.id, s.username, s.display_name, 
               a.login_time, a.last_activity, a.session_token
        FROM active_sessions a
        JOIN sellers s ON a.seller_id = s.id
        WHERE a.is_active = 1
        ORDER BY a.last_activity DESC
    ''').fetchall()
    conn.close()
    
    result = []
    now = datetime.utcnow()
    
    for seller in sellers:
        seller_dict = dict(seller)
        
        login_time_utc = datetime.strptime(seller_dict['login_time'], '%Y-%m-%d %H:%M:%S')
        seller_dict['login_time_local'] = utc_to_local(login_time_utc)
        seller_dict['login_time_short'] = seller_dict['login_time_local'][:5]
        
        last_activity_utc = datetime.strptime(seller_dict['last_activity'], '%Y-%m-%d %H:%M:%S')
        minutes_since_activity = (now - last_activity_utc).total_seconds() / 60
        
        is_really_active = minutes_since_activity < 5
        
        seller_dict['is_really_active'] = is_really_active
        
        if is_really_active:
            seller_dict['status'] = 'active'
            seller_dict['status_class'] = 'success'
            seller_dict['status_text'] = 'Активен'
        elif minutes_since_activity < 30:
            seller_dict['status'] = 'inactive'
            seller_dict['status_class'] = 'warning'
            seller_dict['status_text'] = 'Неактивен'
        else:
            seller_dict['status'] = 'very_inactive'
            seller_dict['status_class'] = 'secondary'
            seller_dict['status_text'] = 'Давно неактивен'
        
        result.append(seller_dict)
    
    return result

def process_single_device_login(seller, flask_request):
    """Создание новой сессии с удалением старых"""
    conn = get_db()
    
    try:
        deleted_count = conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', 
                                    (seller['id'],)).rowcount
        
        if deleted_count > 0:
            print(f"🗑️ Удалено {deleted_count} старых сессий для {seller['username']}")
            log_action(seller['id'], 'auto_logout_old', 
                      details=f'Удалено {deleted_count} старых сессий при новом входе')
        
        session_token = secrets.token_hex(32)
        
        conn.execute('''
        INSERT INTO active_sessions (seller_id, session_token, ip_address, user_agent, login_time, last_activity)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            seller['id'], 
            session_token, 
            flask_request.remote_addr, 
            flask_request.user_agent.string[:200],
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        ))
        
        conn.commit()
        
        session['seller_logged_in'] = True
        session['seller_id'] = seller['id']
        session['seller_username'] = seller['username']
        session['display_name'] = seller.get('display_name') or seller['username']
        session['session_token'] = session_token
        
        login_time_utc = datetime.utcnow()
        session['login_time_utc'] = login_time_utc.strftime('%Y-%m-%d %H:%M:%S')
        session['login_time_local'] = utc_to_local(login_time_utc)
        
        conn.execute('UPDATE sellers SET last_login = ? WHERE id = ?',
                    (login_time_utc.strftime('%Y-%m-%d %H:%M:%S'), seller['id']))
        conn.commit()
        
        log_action(seller['id'], 'login', 
                  details=f'Вход с {flask_request.remote_addr}')
        
        print(f"✅ Успешный вход: {seller['username']}")
        
        return redirect(url_for('seller_dashboard'))
        
    except Exception as e:
        print(f"❌ Ошибка при входе для {seller['username']}: {e}")
        return redirect(url_for('seller_login'))
        
    finally:
        conn.close()

def clear_old_pending_logins():
    """Очистка устаревших pending логинов из сессии"""
    pending_login = session.get('pending_login')
    if pending_login:
        if datetime.now().timestamp() - pending_login['timestamp'] > 600:
            session.pop('pending_login', None)
            print("🧹 Очищен устаревший pending логин")

def update_shipment_status_auto(shipment_id):
    """Автоматическое обновление статуса поставки при продаже всех товаров"""
    conn = get_db()
    
    try:
        # Получаем все товары в поставке
        items = conn.execute('''
            SELECT status FROM items WHERE shipment_id = ?
        ''', (shipment_id,)).fetchall()
        
        if not items:
            return
        
        all_sold = True
        for item in items:
            if item['status'] not in ['продано', 'взял себе']:
                all_sold = False
                break
        
        if all_sold:
            # Обновляем статус поставки на "продано"
            conn.execute('''
            UPDATE shipments 
            SET status = 'продано', updated_at = ?
            WHERE id = ?
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
            
            conn.commit()
            print(f"✅ Поставка {shipment_id} автоматически переведена в статус 'продано'")
            
    except Exception as e:
        print(f"Ошибка при автоматическом обновлении статуса поставки: {e}")
    finally:
        conn.close()

# ==================== НОВЫЕ МАРШРУТЫ ДЛЯ ПОСТАВОК ====================

@app.route('/seller/shipments')
def get_shipments():
    """Получить список всех поставок"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = get_db()
    shipments = conn.execute('''
        SELECT * FROM shipments 
        ORDER BY order_date DESC, id DESC
    ''').fetchall()
    conn.close()
    
    shipments_list = [dict(ship) for ship in shipments]
    return jsonify({'shipments': shipments_list})

@app.route('/seller/shipments/create_with_items', methods=['POST'])
def create_shipment_with_items():
    """Создать поставку с товарами"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Генерируем номер поставки
        last_shipment = conn.execute(
            'SELECT shipment_number FROM shipments ORDER BY id DESC LIMIT 1'
        ).fetchone()
        
        if last_shipment and last_shipment['shipment_number'].startswith('SHIP-'):
            last_num = int(last_shipment['shipment_number'].split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        shipment_number = f"SHIP-{new_num:03d}"
        
        # Создаем поставку
        cursor.execute('''
        INSERT INTO shipments (shipment_number, order_date, delivery_cost, status)
        VALUES (?, ?, ?, ?)
        ''', (
            shipment_number,
            data['order_date'],
            0,  # Доставка пока 0, будет добавлена позже
            'в пути'
        ))
        
        shipment_id = cursor.lastrowid
        
        # Добавляем товары
        items = data.get('items', [])
        added_count = 0
        
        for item_data in items:
            cursor.execute('''
            INSERT INTO items (name, cost_price, sell_price, status, 
                             shipment_id, date_arrived, manual_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_data['name'],
                float(item_data['cost_price']),
                float(item_data['sell_price']),
                'в пути',
                shipment_id,
                data['order_date'],
                float(item_data['sell_price'])
            ))
            added_count += 1
        
        # Обновляем счетчик товаров
        cursor.execute('''
        UPDATE shipments 
        SET total_items = ?, updated_at = ?
        WHERE id = ?
        ''', (added_count, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        conn.commit()
        conn.close()
        
        log_action(session['seller_id'], 'add_shipment', 
                  details=f'Создана поставка {shipment_number} с {added_count} товарами')
        
        return jsonify({
            'success': True, 
            'shipment_id': shipment_id,
            'shipment_number': shipment_number,
            'added_count': added_count
        })
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка создания поставки: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/shipments/<int:shipment_id>/add_items', methods=['POST'])
def add_items_to_shipment(shipment_id):
    """Добавить товары в существующую поставку"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        items = data['items']
        
        conn = get_db()
        cursor = conn.cursor()
        
        shipment = conn.execute(
            'SELECT * FROM shipments WHERE id = ?', 
            (shipment_id,)
        ).fetchone()
        
        if not shipment:
            conn.close()
            return jsonify({'error': 'Поставка не найдена'}), 404
        
        added_count = 0
        for item_data in items:
            cursor.execute('''
            INSERT INTO items (name, cost_price, sell_price, status, 
                             shipment_id, date_arrived, manual_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_data['name'],
                float(item_data['cost_price']),
                float(item_data['sell_price']),
                shipment['status'],  # Используем статус поставки
                shipment_id,
                shipment['order_date'],
                float(item_data['sell_price'])
            ))
            added_count += 1
        
        # Обновляем счетчик товаров
        cursor.execute('''
        UPDATE shipments 
        SET total_items = total_items + ?, updated_at = ?
        WHERE id = ?
        ''', (added_count, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        conn.commit()
        conn.close()
        
        log_action(session['seller_id'], 'add_items_to_shipment', 
                  details=f'Добавлено {added_count} товаров в поставку #{shipment_id}')
        
        return jsonify({
            'success': True, 
            'added_count': added_count
        })
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка добавления товаров: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/shipments/<int:shipment_id>/update_status', methods=['POST'])
def update_shipment_status(shipment_id):
    """Обновить статус поставки и добавить транзакцию доставки"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        new_status = data['status']
        delivery_cost = float(data.get('delivery_cost', 0))
        received_date = data.get('received_date', datetime.now().strftime('%Y-%m-%d'))
        
        if new_status not in ['в наличии', 'продано']:
            return jsonify({'error': 'Недопустимый статус'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Получаем текущий статус поставки
        shipment = conn.execute(
            'SELECT status, shipment_number FROM shipments WHERE id = ?', 
            (shipment_id,)
        ).fetchone()
        
        if not shipment:
            conn.close()
            return jsonify({'error': 'Поставка не найдена'}), 404
        
        old_status = shipment['status']
        
        # Обновляем статус поставки и стоимость доставки
        cursor.execute('''
        UPDATE shipments 
        SET status = ?, received_date = ?, delivery_cost = ?, updated_at = ?
        WHERE id = ?
        ''', (new_status, received_date, delivery_cost,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        if new_status == 'в наличии':
            # Обновляем статус товаров на "в наличии"
            cursor.execute('''
            UPDATE items 
            SET status = 'в наличии', date_arrived = ?
            WHERE shipment_id = ? AND status != 'продано' AND status != 'взял себе'
            ''', (received_date, shipment_id))
            
            # Добавляем транзакцию доставки (отрицательная сумма)
            if delivery_cost > 0:
                cursor.execute('''
                INSERT INTO transactions (date, type, shipment_id, amount, note)
                VALUES (?, ?, ?, ?, ?)
                ''', (
                    received_date,
                    'delivery',
                    shipment_id,
                    -delivery_cost,
                    f'Доставка поставки {shipment["shipment_number"]}'
                ))
            
            # Добавляем транзакции покупки для каждого товара
            items = conn.execute('''
            SELECT id, name, cost_price FROM items 
            WHERE shipment_id = ? AND status = 'в наличии'
            ''', (shipment_id,)).fetchall()
            
            for item in items:
                existing_tx = conn.execute('''
                SELECT tx_id FROM transactions 
                WHERE item_id = ? AND type = 'purchase'
                ''', (item['id'],)).fetchone()
                
                if not existing_tx:
                    cursor.execute('''
                    INSERT INTO transactions (date, type, item_id, amount, note)
                    VALUES (?, ?, ?, ?, ?)
                    ''', (
                        received_date,
                        'purchase',
                        item['id'],
                        -float(item['cost_price']),
                        f'Покупка {item["name"]}'
                    ))
        
        conn.commit()
        conn.close()
        
        log_action(session['seller_id'], 'update_shipment', 
                  details=f'Статус поставки #{shipment_id} изменен: {old_status} -> {new_status}, доставка: {delivery_cost} BYN')
        
        return jsonify({'success': True})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка обновления статуса поставки: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/items/<int:item_id>/update_price', methods=['POST'])
def update_item_price(item_id):
    """Обновить цену продажи товара"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        new_price = float(data['sell_price'])
        
        conn = get_db()
        
        conn.execute('''
        UPDATE items 
        SET manual_price = ?
        WHERE id = ?
        ''', (new_price, item_id))
        
        conn.commit()
        conn.close()
        
        log_action(session['seller_id'], 'update_item_price', item_id,
                  f'Цена изменена на {new_price} BYN')
        
        return jsonify({'success': True})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка обновления цены: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/items/<int:item_id>/delete', methods=['POST'])
def delete_item(item_id):
    """Удалить товар"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        conn = get_db()
        
        item = conn.execute('SELECT name, shipment_id FROM items WHERE id = ?', 
                           (item_id,)).fetchone()
        
        if not item:
            conn.close()
            return jsonify({'error': 'Товар не найден'}), 404
        
        if item['shipment_id']:
            cursor = conn.cursor()
            cursor.execute('''
            UPDATE shipments 
            SET total_items = total_items - 1, updated_at = ?
            WHERE id = ?
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), item['shipment_id']))
        
        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
        
        conn.execute('DELETE FROM transactions WHERE item_id = ?', (item_id,))
        
        conn.commit()
        conn.close()
        
        log_action(session['seller_id'], 'delete_item', 
                  details=f'Удален товар: {item["name"]}')
        
        return jsonify({'success': True})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка удаления товара: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/items/shipment/<int:shipment_id>')
def get_items_by_shipment(shipment_id):
    """Получить товары по ID поставки"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = get_db()
    items = conn.execute('''
        SELECT * FROM items 
        WHERE shipment_id = ?
        ORDER BY id
    ''', (shipment_id,)).fetchall()
    conn.close()
    
    items_list = [dict(item) for item in items]
    return jsonify({'items': items_list})

@app.route('/seller/items/add_with_shipment', methods=['POST'])
def add_item_with_shipment():
    """Добавить товар с привязкой к поставке"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor()
        
        shipment_id = data.get('shipment_id')
        
        if shipment_id:
            # Проверяем существование поставки
            shipment = conn.execute('SELECT * FROM shipments WHERE id = ?', (shipment_id,)).fetchone()
            if not shipment:
                conn.close()
                return jsonify({'error': 'Поставка не найдена'}), 404
            
            # Используем статус поставки
            item_status = shipment['status']
            date_arrived = shipment['order_date']
        else:
            item_status = data['status']
            date_arrived = datetime.now().strftime('%Y-%m-%d') if item_status == 'в наличии' else None
        
        cursor.execute('''
        INSERT INTO items (name, cost_price, sell_price, status, shipment_id, date_arrived, manual_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            float(data['cost_price']),
            float(data['sell_price']),
            item_status,
            shipment_id,
            date_arrived,
            float(data['sell_price'])
        ))
        
        item_id = cursor.lastrowid
        
        # Добавляем транзакцию если товар сразу в наличии
        if item_status == 'в наличии':
            cursor.execute('''
            INSERT INTO transactions (date, type, item_id, amount, note)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                'purchase',
                item_id,
                -float(data['cost_price']),
                f'Покупка {data["name"]}'
            ))
        
        # Обновляем счетчик товаров в поставке
        if shipment_id:
            cursor.execute('''
            UPDATE shipments 
            SET total_items = total_items + 1, updated_at = ?
            WHERE id = ?
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        conn.commit()
        conn.close()
        
        log_action(session['seller_id'], 'add_item', item_id, 
                  f'Добавлен товар: {data["name"]}' + (f' в поставку #{shipment_id}' if shipment_id else ''))
        
        return jsonify({'success': True, 'id': item_id})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', details=f'Ошибка добавления: {str(e)}')
        return jsonify({'error': str(e)}), 400

# ==================== МАРШРУТЫ ====================

@app.context_processor
def inject_now():
    """Добавляет текущую дату во все шаблоны"""
    return {'now': datetime.now()}

@app.route('/')
def index():
    """Перенаправляем сразу на страницу покупателя"""
    return redirect(url_for('buyer'))

@app.route('/buyer')
def buyer():
    """Страница для покупателей"""
    conn = get_db()
    
    # Показываем только товары со статусом "в наличии"
    items = conn.execute('''
        SELECT id, name, sell_price, status, date_arrived, manual_price
        FROM items 
        WHERE status = 'в наличии'
        ORDER BY date_arrived DESC, id DESC
    ''').fetchall()
    
    conn.close()
    
    items_list = [dict(item) for item in items]
    
    # Используем manual_price если есть, иначе sell_price
    for item in items_list:
        item['display_price'] = item['manual_price'] if item['manual_price'] else item['sell_price']
    
    # Получаем активных продавцов
    active_sellers = get_active_sellers()
    really_active_sellers = [s for s in active_sellers if s.get('is_really_active', False)]
    
    return render_template('buyer.html',
                         in_stock=items_list,
                         in_transit=[],  # Не показываем товары в пути покупателям
                         total=len(items_list),
                         active_sellers=really_active_sellers)

@app.before_request
def check_session_middleware():
    """Проверяем валидность сессии для маршрутов продавца"""
    if request.path.startswith('/seller/'):
        excluded_paths = [
            '/seller/login',
            '/seller/logout', 
            '/seller/session_expired',
            '/seller/check_session',
            '/seller/active_sellers_count_public',
            '/seller/active_sellers_list_public',
            '/seller/login_with_override'
        ]
        
        if any(request.path == path or request.path.startswith(path + '/') for path in excluded_paths):
            return
        
        if not session.get('seller_logged_in') or not session.get('session_token'):
            return redirect(url_for('session_expired'))
        
        seller_id = session['seller_id']
        session_token = session['session_token']
        
        conn = get_db()
        current_session = conn.execute('''
            SELECT 1 FROM active_sessions 
            WHERE seller_id = ? AND session_token = ? AND is_active = 1
        ''', (seller_id, session_token)).fetchone()
        conn.close()
        
        if not current_session:
            print(f"🚨 Сессия не найдена! seller_id={seller_id}")
            session.clear()
            return redirect(url_for('session_expired'))

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    """Вход для продавца"""
    clear_old_sessions()
    clear_old_pending_logins()
    
    expired = request.args.get('expired')
    expired_message = None
    if expired:
        expired_message = 'Вы были автоматически выведены из системы с другого устройства.'
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        seller = get_seller_by_username(username)
        
        if seller and bcrypt.check_password_hash(seller['password_hash'], password):
            conn = get_db()
            active_sessions = conn.execute('''
                SELECT * FROM active_sessions 
                WHERE seller_id = ? AND is_active = 1
                ORDER BY last_activity DESC
                LIMIT 1
            ''', (seller['id'],)).fetchall()
            conn.close()
            
            if active_sessions and len(active_sessions) > 0:
                session['pending_login'] = {
                    'username': username,
                    'seller_id': seller['id'],
                    'timestamp': datetime.now().timestamp()
                }
                
                return render_template('login_warning.html',
                                     username=username,
                                     active_session=dict(active_sessions[0]),
                                     expired_message=expired_message)
            
            return process_single_device_login(seller, request)
        else:
            return render_template('seller_login.html', 
                                 error='Неверный логин или пароль',
                                 expired_message=expired_message)
    
    return render_template('seller_login.html', 
                         expired_message=expired_message)

@app.route('/seller/login_with_override', methods=['POST'])
def login_with_override():
    """Вход с завершением предыдущей сессии"""
    pending_login = session.get('pending_login')
    
    if not pending_login:
        return redirect(url_for('seller_login'))
    
    if datetime.now().timestamp() - pending_login['timestamp'] > 600:
        session.pop('pending_login', None)
        return redirect(url_for('seller_login'))
    
    seller = get_seller_by_username(pending_login['username'])
    
    if not seller:
        session.pop('pending_login', None)
        return redirect(url_for('seller_login'))
    
    conn = get_db()
    old_session = conn.execute('''
        SELECT * FROM active_sessions 
        WHERE seller_id = ? AND is_active = 1
    ''', (seller['id'],)).fetchone()
    
    if old_session:
        log_action(seller['id'], 'force_logout', 
                  details=f'Принудительно завершена сессия с IP {old_session["ip_address"]}')
        print(f"🔒 Принудительно завершаем сессию для {pending_login['username']}")
    
    conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', (seller['id'],))
    conn.commit()
    conn.close()
    
    session.pop('pending_login', None)
    
    return process_single_device_login(seller, request)  

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца"""
    if session.get('seller_id'):
        seller_id = session['seller_id']
        username = session.get('seller_username', 'Unknown')
        
        conn = get_db()
        conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', (seller_id,))
        conn.commit()
        conn.close()
        
        log_action(seller_id, 'logout', details=f'Выход из системы ({username})')
    
    session.clear()
    return redirect(url_for('index'))

@app.route('/seller/session_expired')
def session_expired():
    """Страница уведомления о завершенной сессии"""
    return render_template('session_expired.html')

@app.route('/seller/dashboard')
def seller_dashboard():
    """Панель управления продавца"""
    if not session.get('seller_logged_in') or not session.get('session_token'):
        return redirect(url_for('session_expired'))
    
    seller_id = session.get('seller_id')
    session_token = session.get('session_token')
    
    conn = get_db()
    
    try:
        # Проверяем множественные сессии
        active_sessions = conn.execute('''
            SELECT session_token, ip_address, user_agent, login_time, last_activity
            FROM active_sessions 
            WHERE seller_id = ? AND is_active = 1
            ORDER BY last_activity DESC
        ''', (seller_id,)).fetchall()
        
        sessions_list = [dict(sess) for sess in active_sessions]
        
        if len(sessions_list) > 1:
            print(f"⚠️  У пользователя ID {seller_id} найдено {len(sessions_list)} активных сессий:")
            
            current_session_exists = any(sess['session_token'] == session_token for sess in sessions_list)
            
            if current_session_exists:
                conn.execute('''
                DELETE FROM active_sessions 
                WHERE seller_id = ? AND session_token != ?
                ''', (seller_id, session_token))
                conn.commit()
                print(f"✅ Оставлена только текущая сессия")
                
                log_action(seller_id, 'session_cleanup', 
                          details=f'Удалено {len(sessions_list)-1} лишних сессий')
            else:
                print(f"🚨 Текущая сессия не найдена в активных!")
                conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', (seller_id,))
                conn.commit()
                session.clear()
                conn.close()
                return redirect(url_for('seller_login'))
        
        # Проверяем валидность сессии
        current_session = conn.execute('''
            SELECT s.username, s.display_name, a.login_time, a.last_activity
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.session_token = ? AND a.seller_id = ? AND a.is_active = 1
        ''', (session_token, seller_id)).fetchone()
        
        if not current_session:
            print(f"🚨 Сессия не найдена в базе: seller_id={seller_id}")
            session.clear()
            conn.close()
            return redirect(url_for('seller_login'))
        
        # Обновляем время активности
        conn.execute('''
        UPDATE active_sessions 
        SET last_activity = ?
        WHERE session_token = ? AND seller_id = ?
        ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), session_token, seller_id))
        conn.commit()
        
        # Получаем все товары (включая все статусы)
        items = conn.execute('''
            SELECT * FROM items 
            ORDER BY 
                CASE status 
                    WHEN 'в пути' THEN 1
                    WHEN 'в наличии' THEN 2
                    WHEN 'зарезервировано' THEN 3
                    WHEN 'продано' THEN 4
                    WHEN 'взял себе' THEN 5
                    ELSE 6
                END,
                id DESC
        ''').fetchall()
        
        conn.close()
        
        items_list = [dict(item) for item in items]
        
        # Статистика
        stats = {
            'total': len(items_list),
            'in_stock': len([i for i in items_list if i['status'] == 'в наличии']),
            'in_transit': len([i for i in items_list if i['status'] == 'в пути']),
            'reserved': len([i for i in items_list if i['status'] == 'зарезервировано']),
            'sold': len([i for i in items_list if i['status'] == 'продано']),
            'personal': len([i for i in items_list if i['status'] == 'взял себе']),
        }
        
        recent_actions = get_recent_actions(limit=10)
        
        active_sellers_list = get_active_sellers()
        
        active_count = len([s for s in active_sellers_list if s.get('is_really_active', False)])
        
        print(f"✅ Успешный доступ к панели: {current_session['username']}")
        
        return render_template('seller_dashboard.html',
                             items=items_list,
                             stats=stats,
                             recent_actions=recent_actions,
                             active_sellers=active_sellers_list,
                             active_count=active_count,
                             login_time_local=session.get('login_time_local', ''))
                             
    except Exception as e:
        print(f"❌ Критическая ошибка в seller_dashboard: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            conn.close()
        except:
            pass
        
        session.clear()
        return redirect(url_for('seller_login'))

@app.route('/seller/add', methods=['POST'])
def add_item():
    """Добавить товар (AJAX) - устаревший, используйте add_item_with_shipment"""
    return add_item_with_shipment()

@app.route('/seller/update/<int:item_id>', methods=['POST'])
def update_item(item_id):
    """Обновить статус товара (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        new_status = data['status']
        
        conn = get_db()
        
        item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            conn.close()
            return jsonify({'error': 'Товар не найден'}), 404
        
        old_status = item['status']
        
        # Обновляем статус и соответствующую дату
        date_field = ''
        date_value = None
        
        if new_status == 'продано':
            date_field = ', date_sold = ?'
            date_value = datetime.now().strftime('%Y-%m-%d')
        elif new_status == 'взял себе':
            date_field = ', date_taken = ?'
            date_value = datetime.now().strftime('%Y-%m-%d')
        elif new_status == 'зарезервировано':
            date_field = ', date_reserved = ?'
            date_value = datetime.now().strftime('%Y-%m-%d')
        elif new_status == 'в наличии':
            # Если меняем с зарезервировано на в наличии, очищаем дату резерва
            if old_status == 'зарезервировано':
                date_field = ', date_reserved = NULL'
        
        query = f'UPDATE items SET status = ?{date_field} WHERE id = ?'
        
        if date_field and date_value:
            conn.execute(query, (new_status, date_value, item_id))
        elif date_field:
            conn.execute(query, (new_status, item_id))
        else:
            conn.execute(query, (new_status, item_id))
        
        # Добавляем транзакцию продажи
        if old_status != 'продано' and new_status == 'продано':
            sell_price = item['manual_price'] if item['manual_price'] else item['sell_price']
            conn.execute('''
            INSERT INTO transactions (date, type, item_id, amount, note)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                'sale',
                item_id,
                float(sell_price),
                f'Продажа {item["name"]}'
            ))
            
            # Проверяем автоматическое обновление статуса поставки
            if item['shipment_id']:
                update_shipment_status_auto(item['shipment_id'])
        
        conn.commit()
        conn.close()
        
        log_action(session['seller_id'], 'update_item', item_id, 
                  f'Статус изменен: {old_status} -> {new_status}')
        
        return jsonify({'success': True})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', details=f'Ошибка обновления: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/keepalive')
def keepalive():
    """Поддержание активности сессии"""
    if not session.get('seller_logged_in') or not session.get('session_token'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = get_db()
    conn.execute('''
    UPDATE active_sessions 
    SET last_activity = ? 
    WHERE session_token = ? AND seller_id = ?
    ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), session['session_token'], session['seller_id']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/seller/notifications')
def get_notifications():
    """Получить непрочитанные уведомления (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = get_db()
    notifications = conn.execute('''
        SELECT n.*, s.username as from_username, s.display_name as from_display_name
        FROM notifications n
        LEFT JOIN sellers s ON n.from_seller_id = s.id
        WHERE n.seller_id = ? AND n.is_read = 0
        ORDER BY n.created_at DESC
        LIMIT 20
    ''', (session['seller_id'],)).fetchall()
    
    notifications_list = [dict(n) for n in notifications]
    
    if notifications_list:
        conn.execute('UPDATE notifications SET is_read = 1 WHERE seller_id = ? AND is_read = 0', 
                    (session['seller_id'],))
    
    conn.commit()
    conn.close()
    
    return jsonify({'notifications': notifications_list})

@app.route('/seller/notification_count')
def notification_count():
    """Количество непрочитанных уведомлений (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM notifications WHERE seller_id = ? AND is_read = 0', 
                        (session['seller_id'],)).fetchone()[0]
    conn.close()
    
    return jsonify({'count': count})

@app.route('/seller/mark_all_read', methods=['POST'])
def mark_all_read():
    """Пометить все уведомления как прочитанные (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE seller_id = ?', 
                (session['seller_id'],))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/seller/active_sellers')
def get_active_sellers_list():
    """Получить список активных продавцов (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    active_sellers = get_active_sellers()
    return jsonify({'active_sellers': active_sellers})

@app.route('/seller/active_sellers_count_public')
def active_sellers_count_public():
    """Количество активных продавцов (публичный доступ)"""
    clear_old_sessions()
    
    conn = get_db()
    
    five_minutes_ago = (datetime.utcnow() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    
    count = conn.execute('''
        SELECT COUNT(DISTINCT seller_id) as cnt
        FROM active_sessions 
        WHERE is_active = 1 AND last_activity > ?
    ''', (five_minutes_ago,)).fetchone()[0]
    
    conn.close()
    
    return jsonify({'count': count})

@app.route('/seller/active_sellers_list_public')
def active_sellers_list_public():
    """Список активных продавцов (публичный доступ)"""
    clear_old_sessions()
    
    conn = get_db()
    
    five_minutes_ago = (datetime.utcnow() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    
    sellers = conn.execute('''
        SELECT s.username, s.display_name, a.login_time
        FROM active_sessions a
        JOIN sellers s ON a.seller_id = s.id
        WHERE a.is_active = 1 AND a.last_activity > ?
        ORDER BY a.last_activity DESC
        LIMIT 10
    ''', (five_minutes_ago,)).fetchall()
    
    conn.close()
    
    sellers_list = []
    for seller in sellers:
        try:
            login_time = seller['login_time']
            if isinstance(login_time, str):
                utc_time = datetime.strptime(login_time, '%Y-%m-%d %H:%M:%S')
                local_time = utc_time + timedelta(hours=3)
                login_time_short = local_time.strftime('%H:%M')
            else:
                login_time_short = login_time.strftime('%H:%M')
        except:
            login_time_short = seller['login_time'][11:16] if seller['login_time'] and len(seller['login_time']) > 16 else '??:??'
        
        sellers_list.append({
            'username': seller['username'],
            'display_name': seller['display_name'] or seller['username'],
            'login_time_short': login_time_short
        })
    
    return jsonify({'sellers': sellers_list})

@app.route('/seller/check_session')
def check_session():
    """AJAX endpoint для проверки валидности сессии"""
    if not session.get('seller_logged_in') or not session.get('session_token'):
        return jsonify({'valid': False, 'reason': 'no_session'}), 401
    
    seller_id = session['seller_id']
    session_token = session['session_token']
    
    conn = get_db()
    current_session = conn.execute('''
        SELECT 1 FROM active_sessions 
        WHERE seller_id = ? AND session_token = ? AND is_active = 1
    ''', (seller_id, session_token)).fetchone()
    conn.close()
    
    if current_session:
        return jsonify({'valid': True})
    else:
        print(f"🔍 AJAX проверка: сессия не найдена для {seller_id}")
        session.clear()
        return jsonify({'valid': False, 'reason': 'session_replaced'}), 401

@app.route('/buyer/active_sellers')
def buyer_active_sellers():
    """API для получения активных продавцов (AJAX)"""
    conn = get_db()
    
    ten_minutes_ago = (datetime.utcnow() - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        sellers = conn.execute('''
            SELECT s.id, s.username, s.display_name, a.login_time
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.is_active = 1 
            AND a.last_activity > ?
            ORDER BY a.last_activity DESC
        ''', (ten_minutes_ago,)).fetchall()
    except Exception as e:
        print(f"Ошибка получения продавцов: {e}")
        sellers = []
    
    conn.close()
    
    simplified_sellers = []
    for seller in sellers:
        try:
            login_time = seller['login_time']
            if isinstance(login_time, str):
                utc_time = datetime.strptime(login_time, '%Y-%m-%d %H:%M:%S')
                local_time = utc_time + timedelta(hours=3)
                login_time_short = local_time.strftime('%H:%M')
            else:
                login_time_short = login_time.strftime('%H:%M')
        except:
            login_time_short = seller['login_time'][11:16] if seller['login_time'] and len(seller['login_time']) > 16 else '??:??'
        
        simplified_sellers.append({
            'id': seller['id'],
            'username': seller['username'],
            'display_name': seller['display_name'] or seller['username'],
            'login_time_short': login_time_short
        })
    
    return jsonify({'active_sellers': simplified_sellers})

@app.template_filter('utc_to_local')
def utc_to_local_filter(utc_str):
    """Фильтр для преобразования UTC времени в локальное в шаблонах"""
    return utc_to_local(utc_str)

@app.template_filter('truncate')
def truncate_filter(s, length=30):
    """Обрезает строку до указанной длины"""
    if not s:
        return ""
    if len(s) <= length:
        return s
    return s[:length] + "..."

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    # Очищаем старые сессии при запуске
    clear_old_sessions()
    
    # Запускаем сервер
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
[file content end]
