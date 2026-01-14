import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import secrets
import psycopg2
from psycopg2.extras import DictCursor
import urllib.parse as urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
bcrypt = Bcrypt(app)

# ==================== НАСТРОЙКА БАЗЫ ДАННЫХ ====================

def get_db_connection():
    """Подключение к PostgreSQL базе данных Render"""
    try:
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url:
            conn = psycopg2.connect(database_url, sslmode='require')
        else:
            conn = psycopg2.connect(
                database="shop",
                user="postgres",
                password="postgres",
                host="localhost",
                port="5432"
            )
        
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")
        raise e

def get_db():
    """Альтернативная функция для совместимости"""
    return get_db_connection()

def init_db():
    """Инициализация таблиц в PostgreSQL"""
    print("🔄 Начинаю инициализацию базы данных...")
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Таблица товаров
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            cost_price DECIMAL(10,2) NOT NULL,
            sell_price DECIMAL(10,2) NOT NULL,
            manual_price DECIMAL(10,2),
            status TEXT NOT NULL DEFAULT 'в наличии',
            shipment_id INTEGER,
            date_arrived TEXT,
            date_sold TEXT,
            date_taken TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_wholesale BOOLEAN DEFAULT FALSE,
            reserved_until TEXT
        )
        ''')
        
        # Таблица транзакций
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            item_id INTEGER,
            shipment_id INTEGER,
            amount DECIMAL(10,2),
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица продавцов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sellers (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            role TEXT DEFAULT 'seller',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        ''')
        
        # Таблица действий
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_log (
            id SERIAL PRIMARY KEY,
            seller_id INTEGER,
            action_type TEXT NOT NULL,
            item_id INTEGER,
            shipment_id INTEGER,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица активных сессий
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_sessions (
            id SERIAL PRIMARY KEY,
            seller_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
        ''')
        
        # Таблица уведомлений
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            seller_id INTEGER NOT NULL,
            from_seller_id INTEGER,
            message TEXT NOT NULL,
            item_id INTEGER,
            shipment_id INTEGER,
            action_type TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица поставок
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS shipments (
            id SERIAL PRIMARY KEY,
            shipment_number TEXT UNIQUE NOT NULL,
            order_date TEXT NOT NULL,
            received_date TEXT,
            delivery_cost DECIMAL(10,2) DEFAULT 0,
            status TEXT DEFAULT 'в пути',
            total_items INTEGER DEFAULT 0,
            sold_items INTEGER DEFAULT 0,
            is_wholesale BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        print("✅ Таблицы успешно созданы в PostgreSQL")
        
        # Добавляем стандартных продавцов
        print("👥 Проверяю наличие стандартных продавцов...")
        default_sellers = [
            ('SlavchikSV', 'sv280606', 'Администратор', 'admin'),
            ('mkozlov', '020988mama', 'Главный администратор', 'admin'),
            ('g_nix', 'IHHujhg655G', 'Оптовый менеджер', 'seller'),
        ]
        
        for username, password, display, role in default_sellers:
            cursor.execute('SELECT id FROM sellers WHERE username = %s', (username,))
            existing = cursor.fetchone()
            
            if not existing:
                password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
                cursor.execute('''
                INSERT INTO sellers (username, password_hash, display_name, role)
                VALUES (%s, %s, %s, %s)
                ''', (username, password_hash, display, role))
                print(f"✅ Создан продавец: {username}")
        
        conn.commit()
        print("🎉 Инициализация базы данных завершена успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации БД: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# В функции check_and_init_db() добавьте после инициализации:

def check_and_init_db():
    """Проверить и инициализировать БД при запуске"""
    print("🔍 Проверяю состояние базы данных...")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'items'
            )
            """)
            exists = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            if not exists:
                print("📦 Таблицы не найдены, запускаю инициализацию...")
                init_db()
            else:
                print("✅ База данных уже инициализирована")
                # АВТОМАТИЧЕСКИ ДОБАВЛЯЕМ НОВЫЕ СТОЛБЦЫ
                update_database_structure()
            
            return True
            
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            if attempt == max_retries - 1:
                print("❌ Не удалось подключиться к базе данных после нескольких попыток")
                return False
            import time
            time.sleep(2)
    
    return False

def update_database_structure():
    """Добавить недостающие столбцы"""
    print("🔄 Проверяю структуру таблиц...")
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существующие столбцы в items
        cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'items'
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        # Добавляем недостающие столбцы
        missing_columns = []
        
        if 'is_wholesale' not in existing_columns:
            missing_columns.append('is_wholesale BOOLEAN DEFAULT FALSE')
        
        if 'reserved_until' not in existing_columns:
            missing_columns.append('reserved_until TEXT')
        
        if missing_columns:
            print(f"➕ Добавляю недостающие столбцы: {', '.join([col.split()[0] for col in missing_columns])}")
            for column_def in missing_columns:
                try:
                    cursor.execute(f'ALTER TABLE items ADD COLUMN {column_def}')
                    print(f"✅ Добавлен столбец: {column_def.split()[0]}")
                except Exception as e:
                    print(f"⚠️ Ошибка добавления столбца: {e}")
            
            conn.commit()
        
        # Проверяем shipments
        cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'shipments'
        """)
        existing_columns_ship = [row[0] for row in cursor.fetchall()]
        
        if 'is_wholesale' not in existing_columns_ship:
            try:
                cursor.execute('ALTER TABLE shipments ADD COLUMN is_wholesale BOOLEAN DEFAULT FALSE')
                print("✅ Добавлен столбец is_wholesale в shipments")
            except Exception as e:
                print(f"⚠️ Ошибка добавления столбца: {e}")
        
        if 'sold_items' not in existing_columns_ship:
            try:
                cursor.execute('ALTER TABLE shipments ADD COLUMN sold_items INTEGER DEFAULT 0')
                print("✅ Добавлен столбец sold_items в shipments")
            except Exception as e:
                print(f"⚠️ Ошибка добавления столбца: {e}")
        
        if 'is_wholesale' in existing_columns_ship or 'sold_items' in existing_columns_ship:
            conn.commit()
        
        print("🎉 Структура базы данных проверена и обновлена!")
        
    except Exception as e:
        print(f"❌ Ошибка обновления структуры: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Инициализируем БД при импорте модуля
print("=" * 50)
print("🚀 ЗАПУСК ПРИЛОЖЕНИЯ МАГАЗИНА")
print("=" * 50)

db_ready = check_and_init_db()
if not db_ready:
    print("⚠️ ПРЕДУПРЕЖДЕНИЕ: База данных не готова, но приложение запускается")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_seller_by_username(username):
    """Найти продавца по логину"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sellers WHERE username = %s', (username,))
        seller = cursor.fetchone()
        if seller:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, seller))
        return None
    except Exception as e:
        print(f"❌ Ошибка поиска продавца: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def utc_to_local(utc_dt, format_only_time=False):
    """Конвертировать UTC время в локальное"""
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
        
        local_dt = utc_dt + timedelta(hours=3)
        
        if format_only_time:
            return local_dt.strftime('%H:%M')
        else:
            return local_dt.strftime('%d.%m.%Y %H:%M:%S')
            
    except Exception as e:
        print(f"Ошибка конвертации времени {utc_dt}: {e}")
        if isinstance(utc_dt, str) and len(utc_dt) > 10:
            return utc_dt[11:16]
        return str(utc_dt)

def log_action(seller_id, action_type, item_id=None, shipment_id=None, details="", ip_address=None):
    """Записать действие в лог"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        created_at_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
        INSERT INTO action_log (seller_id, action_type, item_id, shipment_id, details, ip_address, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (seller_id, action_type, item_id, shipment_id, details, ip_address or request.remote_addr, created_at_utc))
        
        conn.commit()
        
    except Exception as e:
        print(f"❌ Ошибка при записи лога: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def clear_old_sessions():
    """Очистка старых неактивных сессий"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        DELETE FROM active_sessions 
        WHERE last_activity < NOW() - INTERVAL '8 hours'
        ''')
        
        deleted = cursor.rowcount
        conn.commit()
        
        if deleted > 0:
            print(f"🧹 Очищено {deleted} старых сессий")
            
    except Exception as e:
        print(f"⚠️ Ошибка при очистке сессий: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_active_sellers():
    """Получить список активных продавцов"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.id, s.username, s.display_name, 
                   a.login_time, a.last_activity, a.session_token
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.is_active = TRUE
            ORDER BY a.last_activity DESC
        ''')
        
        sellers = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        result = []
        now = datetime.utcnow()
        
        for seller_tuple in sellers:
            seller_dict = dict(zip(columns, seller_tuple))
            
            if seller_dict['login_time']:
                login_time_utc = seller_dict['login_time']
                if isinstance(login_time_utc, str):
                    try:
                        login_time_utc = datetime.strptime(login_time_utc, '%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                seller_dict['login_time_local'] = utc_to_local(login_time_utc)
                seller_dict['login_time_short'] = seller_dict['login_time_local'][11:16] if seller_dict['login_time_local'] else ''
            
            result.append(seller_dict)
        
        return result
        
    except Exception as e:
        print(f"❌ Ошибка получения активных продавцов: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def process_single_device_login(seller, flask_request):
    """Создание новой сессии с удалением старых"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM active_sessions WHERE seller_id = %s', (seller['id'],))
        
        session_token = secrets.token_hex(32)
        
        cursor.execute('''
        INSERT INTO active_sessions (seller_id, session_token, ip_address, user_agent, login_time, last_activity)
        VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            seller['id'], 
            session_token, 
            flask_request.remote_addr, 
            flask_request.user_agent.string[:200],
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        ))
        
        cursor.execute('UPDATE sellers SET last_login = %s WHERE id = %s',
                      (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), seller['id']))
        
        conn.commit()
        
        session['seller_logged_in'] = True
        session['seller_id'] = seller['id']
        session['seller_username'] = seller['username']
        session['display_name'] = seller.get('display_name') or seller['username']
        session['session_token'] = session_token
        
        login_time_utc = datetime.utcnow()
        session['login_time_utc'] = login_time_utc.strftime('%Y-%m-%d %H:%M:%S')
        session['login_time_local'] = utc_to_local(login_time_utc)
        
        log_action(seller['id'], 'login', details=f'Вход с {flask_request.remote_addr}')
        
        print(f"✅ Успешный вход: {seller['username']}")
        
        return redirect(url_for('seller_dashboard'))
        
    except Exception as e:
        print(f"❌ Ошибка при входе: {e}")
        if conn:
            conn.rollback()
        return redirect(url_for('seller_login'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def update_shipment_status_auto(shipment_id):
    """Автоматически обновить статус поставки на проданную"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем информацию о поставке
        cursor.execute('SELECT total_items, sold_items FROM shipments WHERE id = %s', (shipment_id,))
        shipment = cursor.fetchone()
        
        if shipment and shipment[0] > 0 and shipment[0] == shipment[1]:
            cursor.execute('UPDATE shipments SET status = %s WHERE id = %s', ('продано', shipment_id))
            conn.commit()
            print(f"✅ Поставка #{shipment_id} автоматически помечена как проданная")
            
    except Exception as e:
        print(f"❌ Ошибка автообновления статуса поставки: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
    """Страница для покупателей (только розничные товары в наличии)"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, sell_price, status, date_arrived, manual_price
            FROM items 
            WHERE status = 'в наличии' 
            AND is_wholesale = FALSE
            AND (reserved_until IS NULL OR reserved_until < %s)
            ORDER BY date_arrived DESC, id DESC
        ''', (datetime.now().strftime('%Y-%m-%d'),))
        
        items = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        items_list = []
        for item_tuple in items:
            item_dict = dict(zip(columns, item_tuple))
            item_dict['display_price'] = item_dict.get('manual_price') or item_dict['sell_price']
            items_list.append(item_dict)
        
        # Получаем активных продавцов
        active_sellers = get_active_sellers()
        
        return render_template('buyer.html',
                             items=items_list,
                             total=len(items_list),
                             active_sellers=active_sellers)
                             
    except Exception as e:
        print(f"❌ Ошибка в buyer: {e}")
        return render_template('buyer.html',
                             items=[],
                             total=0,
                             active_sellers=[])
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/wholesale')
def wholesale():
    """Страница для оптовых покупателей (только оптовые товары)"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, sell_price, status, date_arrived, manual_price
            FROM items 
            WHERE status = 'в наличии' 
            AND is_wholesale = TRUE
            ORDER BY date_arrived DESC, id DESC
        ''')
        
        items = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        items_list = []
        for item_tuple in items:
            item_dict = dict(zip(columns, item_tuple))
            item_dict['display_price'] = item_dict.get('manual_price') or item_dict['sell_price']
            items_list.append(item_dict)
        
        return render_template('wholesale.html',
                             items=items_list,
                             total=len(items_list))
                             
    except Exception as e:
        print(f"❌ Ошибка в wholesale: {e}")
        return render_template('wholesale.html',
                             items=[],
                             total=0)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
        
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 1 FROM active_sessions 
                WHERE seller_id = %s AND session_token = %s AND is_active = TRUE
            ''', (seller_id, session_token))
            
            current_session = cursor.fetchone()
            
            if not current_session:
                session.clear()
                return redirect(url_for('session_expired'))
                
        except Exception as e:
            print(f"❌ Ошибка проверки сессии: {e}")
            session.clear()
            return redirect(url_for('session_expired'))
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    """Вход для продавца"""
    clear_old_sessions()
    
    expired = request.args.get('expired')
    expired_message = None
    if expired:
        expired_message = 'Вы были автоматически выведены из системы с другого устройства.'
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        seller = get_seller_by_username(username)
        
        if seller and bcrypt.check_password_hash(seller['password_hash'], password):
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM active_sessions 
                    WHERE seller_id = %s AND is_active = TRUE
                    ORDER BY last_activity DESC
                    LIMIT 1
                ''', (seller['id'],))
                
                active_sessions = cursor.fetchall()
                
                if active_sessions and len(active_sessions) > 0:
                    session['pending_login'] = {
                        'username': username,
                        'seller_id': seller['id'],
                        'timestamp': datetime.now().timestamp()
                    }
                    
                    return render_template('login_warning.html',
                                         username=username,
                                         expired_message=expired_message)
                
                return process_single_device_login(seller, request)
                
            except Exception as e:
                print(f"❌ Ошибка проверки сессий: {e}")
                return redirect(url_for('seller_login'))
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
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
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM active_sessions WHERE seller_id = %s', (seller['id'],))
        conn.commit()
        
        session.pop('pending_login', None)
        
        return process_single_device_login(seller, request)
        
    except Exception as e:
        print(f"❌ Ошибка принудительного входа: {e}")
        return redirect(url_for('seller_login'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца"""
    if session.get('seller_id'):
        seller_id = session['seller_id']
        username = session.get('seller_username', 'Unknown')
        
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM active_sessions WHERE seller_id = %s', (seller_id,))
            conn.commit()
            
            log_action(seller_id, 'logout', details=f'Выход из системы ({username})')
            
        except Exception as e:
            print(f"❌ Ошибка при выходе: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    session.clear()
    return redirect(url_for('buyer'))

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
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.username, s.display_name, a.login_time, a.last_activity
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.session_token = %s AND a.seller_id = %s AND a.is_active = TRUE
        ''', (session_token, seller_id))
        
        current_session = cursor.fetchone()
        
        if not current_session:
            session.clear()
            return redirect(url_for('seller_login'))
        
        cursor.execute('''
        UPDATE active_sessions 
        SET last_activity = %s
        WHERE session_token = %s AND seller_id = %s
        ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), session_token, seller_id))
        
        # Получаем все товары
        cursor.execute('''
            SELECT i.*, s.shipment_number 
            FROM items i
            LEFT JOIN shipments s ON i.shipment_id = s.id
            ORDER BY 
                CASE i.status 
                    WHEN 'в наличии' THEN 1
                    WHEN 'зарезервировано' THEN 2
                    WHEN 'в пути' THEN 3
                    WHEN 'продано' THEN 4
                    WHEN 'взял себе' THEN 5
                    ELSE 6
                END,
                i.id DESC
        ''')
        
        items = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        items_list = []
        for item_tuple in items:
            items_list.append(dict(zip(columns, item_tuple)))
        
        # Получаем все поставки
        cursor.execute('SELECT * FROM shipments ORDER BY id DESC')
        shipments = cursor.fetchall()
        shipments_columns = [desc[0] for desc in cursor.description]
        
        shipments_list = []
        for shipment_tuple in shipments:
            shipments_list.append(dict(zip(shipments_columns, shipment_tuple)))
        
        # Статистика
        cursor.execute('SELECT COUNT(*) FROM items WHERE status = %s', ('в наличии',))
        in_stock = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM items WHERE status = %s', ('продано',))
        sold = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM items WHERE status = %s', ('в пути',))
        in_transit = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM items WHERE status = %s', ('зарезервировано',))
        reserved = cursor.fetchone()[0]
        
        stats = {
            'total': len(items_list),
            'in_stock': in_stock,
            'sold': sold,
            'in_transit': in_transit,
            'reserved': reserved,
            'personal': len([i for i in items_list if i['status'] == 'взял себе']),
        }
        
        conn.commit()
        
        # Активные продавцы
        active_sellers_list = get_active_sellers()
        
        return render_template('seller_dashboard.html',
                             items=items_list,
                             shipments=shipments_list,
                             stats=stats,
                             active_sellers=active_sellers_list,
                             login_time_local=session.get('login_time_local', ''))
                             
    except Exception as e:
        print(f"❌ Ошибка в dashboard: {e}")
        session.clear()
        return redirect(url_for('seller_login'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/finance')
def finance():
    """Страница финансового учета"""
    if not session.get('seller_logged_in'):
        return redirect(url_for('seller_login'))
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем все транзакции
        cursor.execute('''
            SELECT t.*, i.name as item_name, s.shipment_number
            FROM transactions t
            LEFT JOIN items i ON t.item_id = i.id
            LEFT JOIN shipments s ON t.shipment_id = s.id
            ORDER BY t.date DESC, t.created_at DESC
        ''')
        
        transactions = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        transactions_list = []
        for tx_tuple in transactions:
            transactions_list.append(dict(zip(columns, tx_tuple)))
        
        # Подсчет итогов
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = %s', ('sale',))
        total_sales = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = %s', ('purchase',))
        total_purchases = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = %s', ('delivery',))
        total_delivery = cursor.fetchone()[0] or 0
        
        profit = total_sales + total_purchases + total_delivery  # purchases отрицательные
        
        return render_template('finance.html',
                             transactions=transactions_list,
                             total_sales=total_sales,
                             total_purchases=total_purchases,
                             total_delivery=total_delivery,
                             profit=profit)
                             
    except Exception as e:
        print(f"❌ Ошибка в finance: {e}")
        return render_template('finance.html',
                             transactions=[],
                             total_sales=0,
                             total_purchases=0,
                             total_delivery=0,
                             profit=0)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/logs')
def view_logs():
    """Страница просмотра логов"""
    if not session.get('seller_logged_in'):
        return redirect(url_for('seller_login'))
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем логи
        cursor.execute('''
            SELECT al.*, s.username, s.display_name
            FROM action_log al
            LEFT JOIN sellers s ON al.seller_id = s.id
            ORDER BY al.created_at DESC
            LIMIT 500
        ''')
        
        logs = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        logs_list = []
        for log_tuple in logs:
            log_dict = dict(zip(columns, log_tuple))
            
            if log_dict['created_at']:
                try:
                    utc_time = log_dict['created_at']
                    if isinstance(utc_time, str):
                        utc_time = datetime.strptime(utc_time, '%Y-%m-%d %H:%M:%S')
                    local_time = utc_time + timedelta(hours=3)
                    log_dict['created_at_local'] = local_time.strftime('%d.%m.%Y %H:%M:%S')
                except:
                    log_dict['created_at_local'] = str(log_dict['created_at'])
            else:
                log_dict['created_at_local'] = ''
            
            logs_list.append(log_dict)
        
        return render_template('logs.html', logs=logs_list)
        
    except Exception as e:
        print(f"❌ Ошибка получения логов: {e}")
        return render_template('logs.html', logs=[])
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/add', methods=['POST'])
def add_item():
    """Добавить товар"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO items (name, cost_price, sell_price, status, date_arrived, is_wholesale, shipment_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (
            data['name'],
            float(data['cost_price']),
            float(data['sell_price']),
            data['status'],
            datetime.now().strftime('%Y-%m-%d') if data['status'] != 'в пути' else None,
            data.get('is_wholesale', False),
            data.get('shipment_id')
        ))
        
        item_id = cursor.fetchone()[0]
        
        # Если товар сразу в наличии, добавляем транзакцию покупки
        if data['status'] == 'в наличии':
            cursor.execute('''
            INSERT INTO transactions (date, type, item_id, amount, note)
            VALUES (%s, %s, %s, %s, %s)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                'purchase',
                item_id,
                -float(data['cost_price']),
                f'Покупка {data["name"]}'
            ))
        
        conn.commit()
        
        log_action(session['seller_id'], 'add_item', item_id=item_id, 
                  details=f'Добавлен товар: {data["name"]}')
        
        return jsonify({'success': True, 'id': item_id})
        
    except Exception as e:
        print(f"❌ Ошибка добавления товара: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка добавления: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/update/<int:item_id>', methods=['POST'])
def update_item(item_id):
    """Обновить статус товара"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        new_status = data['status']
        reserved_until = data.get('reserved_until')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM items WHERE id = %s', (item_id,))
        item_tuple = cursor.fetchone()
        
        if not item_tuple:
            return jsonify({'error': 'Товар не найден'}), 404
        
        columns = [desc[0] for desc in cursor.description]
        item = dict(zip(columns, item_tuple))
        
        old_status = item['status']
        
        # Обновляем статус
        if new_status == 'продано':
            cursor.execute('UPDATE items SET status = %s, date_sold = %s, reserved_until = NULL WHERE id = %s',
                          (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        elif new_status == 'взял себе':
            cursor.execute('UPDATE items SET status = %s, date_taken = %s, reserved_until = NULL WHERE id = %s',
                          (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        elif new_status == 'зарезервировано' and reserved_until:
            cursor.execute('UPDATE items SET status = %s, reserved_until = %s WHERE id = %s',
                          (new_status, reserved_until, item_id))
        else:
            cursor.execute('UPDATE items SET status = %s, reserved_until = NULL WHERE id = %s', 
                          (new_status, item_id))
        
        # Добавляем транзакцию продажи
        if old_status != 'продано' and new_status == 'продано':
            sale_price = item.get('manual_price') or item['sell_price']
            cursor.execute('''
            INSERT INTO transactions (date, type, item_id, amount, note)
            VALUES (%s, %s, %s, %s, %s)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                'sale',
                item_id,
                float(sale_price),
                f'Продажа {item["name"]}'
            ))
            
            # Увеличиваем счетчик проданных в поставке
            if item['shipment_id']:
                cursor.execute('''
                UPDATE shipments 
                SET sold_items = sold_items + 1 
                WHERE id = %s
                ''', (item['shipment_id'],))
                
                # Проверяем, все ли товары в поставке проданы
                update_shipment_status_auto(item['shipment_id'])
        
        # Если меняем с "в наличии" на другой статус после того как товар был куплен
        elif old_status == 'в наличии' and new_status != 'в наличии':
            # Уже есть транзакция покупки, ничего не делаем
            pass
        
        conn.commit()
        
        log_action(session['seller_id'], 'update_item', item_id=item_id, 
                  details=f'Статус изменен: {old_status} -> {new_status}')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка обновления товара: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка обновления: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/shipments')
def get_shipments():
    """Получить список всех поставок"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM shipments ORDER BY id DESC')
        shipments = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        shipments_list = []
        for shipment_tuple in shipments:
            shipments_list.append(dict(zip(columns, shipment_tuple)))
        
        return jsonify({'shipments': shipments_list})
        
    except Exception as e:
        print(f"❌ Ошибка получения поставок: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/shipments/create', methods=['POST'])
def create_shipment():
    """Создать новую поставку"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Генерируем номер поставки
        cursor.execute('SELECT shipment_number FROM shipments ORDER BY id DESC LIMIT 1')
        last_shipment = cursor.fetchone()
        
        if last_shipment and last_shipment[0].startswith('SHIP-'):
            last_num = int(last_shipment[0].split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        shipment_number = f"SHIP-{new_num:03d}"
        
        cursor.execute('''
        INSERT INTO shipments (shipment_number, order_date, status, is_wholesale)
        VALUES (%s, %s, %s, %s) RETURNING id
        ''', (
            shipment_number,
            data['order_date'],
            'в пути',
            data.get('is_wholesale', False)
        ))
        
        shipment_id = cursor.fetchone()[0]
        
        conn.commit()
        
        log_action(session['seller_id'], 'create_shipment', shipment_id=shipment_id,
                  details=f'Создана поставка {shipment_number}')
        
        return jsonify({
            'success': True, 
            'shipment_id': shipment_id,
            'shipment_number': shipment_number
        })
        
    except Exception as e:
        print(f"❌ Ошибка создания поставки: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка создания поставки: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/shipments/<int:shipment_id>/add_items', methods=['POST'])
def add_items_to_shipment(shipment_id):
    """Добавить товары в поставку"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        items = data['items']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем информацию о поставке
        cursor.execute('SELECT * FROM shipments WHERE id = %s', (shipment_id,))
        shipment_tuple = cursor.fetchone()
        
        if not shipment_tuple:
            return jsonify({'error': 'Поставка не найдена'}), 404
        
        columns = [desc[0] for desc in cursor.description]
        shipment = dict(zip(columns, shipment_tuple))
        
        added_items = []
        total_cost = 0
        
        for item_data in items:
            cursor.execute('''
            INSERT INTO items (name, cost_price, sell_price, status, 
                             shipment_id, date_arrived, is_wholesale)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            ''', (
                item_data['name'],
                float(item_data['cost_price']),
                float(item_data['sell_price']),
                'в пути',
                shipment_id,
                None,
                shipment['is_wholesale']
            ))
            
            item_id = cursor.fetchone()[0]
            added_items.append({
                'id': item_id,
                'name': item_data['name']
            })
            
            total_cost += float(item_data['cost_price'])
        
        # Обновляем счетчик товаров
        cursor.execute('''
        UPDATE shipments 
        SET total_items = total_items + %s, updated_at = %s
        WHERE id = %s
        ''', (len(items), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        conn.commit()
        
        log_action(session['seller_id'], 'add_items_to_shipment', shipment_id=shipment_id,
                  details=f'Добавлено {len(items)} товаров в поставку #{shipment_id}')
        
        return jsonify({
            'success': True, 
            'added_count': len(items),
            'total_cost': total_cost,
            'items': added_items
        })
        
    except Exception as e:
        print(f"❌ Ошибка добавления товаров: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка добавления товаров: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/shipments/<int:shipment_id>/update_status', methods=['POST'])
def update_shipment_status(shipment_id):
    """Обновить статус поставки и стоимость доставки"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        new_status = data['status']
        delivery_cost = float(data.get('delivery_cost', 0))
        received_date = data.get('received_date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем текущий статус
        cursor.execute('SELECT status FROM shipments WHERE id = %s', (shipment_id,))
        current_status = cursor.fetchone()
        
        if not current_status:
            return jsonify({'error': 'Поставка не найдена'}), 404
        
        if current_status[0] == 'в наличии' and new_status == 'в пути':
            return jsonify({'error': 'Нельзя изменить статус с "в наличии" на "в пути"'}), 400
        
        # Обновляем статус поставки
        cursor.execute('''
        UPDATE shipments 
        SET status = %s, received_date = %s, delivery_cost = %s, updated_at = %s
        WHERE id = %s
        ''', (new_status, received_date, delivery_cost,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        # Если меняем на "в наличии"
        if new_status == 'в наличии':
            # Обновляем статус товаров
            cursor.execute('''
            UPDATE items 
            SET status = %s, date_arrived = %s
            WHERE shipment_id = %s AND status = 'в пути'
            ''', (new_status, received_date, shipment_id))
            
            # Получаем общую стоимость товаров в поставке
            cursor.execute('''
            SELECT COALESCE(SUM(cost_price), 0) FROM items 
            WHERE shipment_id = %s
            ''', (shipment_id,))
            
            total_cost = cursor.fetchone()[0] or 0
            
            # Добавляем транзакцию покупки товаров
            cursor.execute('''
            INSERT INTO transactions (date, type, shipment_id, amount, note)
            VALUES (%s, %s, %s, %s, %s)
            ''', (
                received_date,
                'purchase',
                shipment_id,
                -float(total_cost),
                f'Покупка товаров поставки #{shipment_id}'
            ))
            
            # Добавляем транзакцию доставки
            if delivery_cost > 0:
                cursor.execute('''
                INSERT INTO transactions (date, type, shipment_id, amount, note)
                VALUES (%s, %s, %s, %s, %s)
                ''', (
                    received_date,
                    'delivery',
                    shipment_id,
                    -float(delivery_cost),
                    f'Доставка поставки #{shipment_id}'
                ))
        
        conn.commit()
        
        log_action(session['seller_id'], 'update_shipment_status', shipment_id=shipment_id,
                  details=f'Статус поставки #{shipment_id} изменен на "{new_status}"')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка обновления статуса: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка обновления статуса поставки: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/items/<int:item_id>/update_price', methods=['POST'])
def update_item_price(item_id):
    """Обновить цену товара"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        new_price = float(data['sell_price'])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE items SET manual_price = %s WHERE id = %s', (new_price, item_id))
        conn.commit()
        
        log_action(session['seller_id'], 'update_item_price', item_id=item_id,
                  details=f'Цена изменена на {new_price} BYN')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка обновления цены: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка обновления цены: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/items/<int:item_id>/delete', methods=['POST'])
def delete_item(item_id):
    """Удалить товар"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT name, shipment_id FROM items WHERE id = %s', (item_id,))
        item_tuple = cursor.fetchone()
        
        if not item_tuple:
            return jsonify({'error': 'Товар не найден'}), 404
        
        item_name = item_tuple[0]
        shipment_id = item_tuple[1]
        
        if shipment_id:
            cursor.execute('''
            UPDATE shipments 
            SET total_items = total_items - 1, updated_at = %s
            WHERE id = %s
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        cursor.execute('DELETE FROM items WHERE id = %s', (item_id,))
        cursor.execute('DELETE FROM transactions WHERE item_id = %s', (item_id,))
        
        conn.commit()
        
        log_action(session['seller_id'], 'delete_item', 
                  details=f'Удален товар: {item_name} (ID: {item_id})')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка удаления товара: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка удаления товара: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/shipments/<int:shipment_id>/delete', methods=['POST'])
def delete_shipment(shipment_id):
    """Удалить поставку"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем есть ли товары в поставке
        cursor.execute('SELECT COUNT(*) FROM items WHERE shipment_id = %s', (shipment_id,))
        item_count = cursor.fetchone()[0]
        
        if item_count > 0:
            return jsonify({'error': f'Невозможно удалить поставку: в ней {item_count} товаров'}), 400
        
        cursor.execute('DELETE FROM shipments WHERE id = %s', (shipment_id,))
        cursor.execute('DELETE FROM transactions WHERE shipment_id = %s', (shipment_id,))
        
        conn.commit()
        
        log_action(session['seller_id'], 'delete_shipment', 
                  details=f'Удалена поставка #{shipment_id}')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка удаления поставки: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', details=f'Ошибка удаления поставки: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/clear_logs', methods=['POST'])
def clear_logs():
    """Очистить логи"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM action_log')
        cursor.execute('DELETE FROM notifications')
        
        conn.commit()
        
        log_action(session['seller_id'], 'clear_logs', 
                  details='Очищены все логи')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка очистки логов: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/keepalive')
def keepalive():
    """Поддержание активности сессии"""
    if not session.get('seller_logged_in') or not session.get('session_token'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE active_sessions 
        SET last_activity = %s 
        WHERE session_token = %s AND seller_id = %s
        ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), session['session_token'], session['seller_id']))
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка keepalive: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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

# ==================== ЗАПУСК СЕРВЕРА ====================

if __name__ == '__main__':
    clear_old_sessions()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)


