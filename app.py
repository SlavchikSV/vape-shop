import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import secrets
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor
import urllib.parse as urlparse
import atexit

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
bcrypt = Bcrypt(app)

# ==================== НАСТРОЙКА БАЗЫ ДАННЫХ ====================

def get_db_connection():
    """Подключение к PostgreSQL базе данных Render"""
    try:
        # Получаем URL базы данных из переменных окружения Render
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url:
            # Для Render - используем SSL
            conn = psycopg2.connect(database_url, sslmode='require')
        else:
            # Для локальной разработки
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
    """Инициализация таблиц в PostgreSQL (автоматически при первом запуске)"""
    print("🔄 Начинаю инициализацию базы данных...")
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Создаем таблицу items если не существует
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица транзакций
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            tx_id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            item_id INTEGER,
            amount DECIMAL(10,2),
            note TEXT
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        print("✅ Таблицы успешно созданы в PostgreSQL")
        
        # Добавляем стандартных продавцов
        print("👥 Проверяю наличие стандартных продавцов...")
        default_sellers = [
            ('SlavchikSV', 'sv280606', 'SysAdmin/GM', 'admin'),
            ('mkozlov', '020988mama', 'Главный администратор', 'admin'),
            ('g_nix', 'IHHujhg655G', 'Продавец', 'seller'),  # Новый продавец
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

def check_and_init_db():
    """Проверить и инициализировать БД при запуске"""
    print("🔍 Проверяю состояние базы данных...")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Проверяем есть ли таблица items
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
            
            # Показываем информацию о таблицах
            show_db_info()
            return True
            
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            if attempt == max_retries - 1:
                print("❌ Не удалось подключиться к базе данных после нескольких попыток")
                return False
            import time
            time.sleep(2)
    
    return False

def show_db_info():
    """Показать информацию о таблицах в БД"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
        """)
        tables = cursor.fetchall()
        
        print("\n📊 ТАБЛИЦЫ В БАЗЕ ДАННЫХ:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"  - {table[0]}: {count} записей")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Не удалось получить информацию о таблицах: {e}")

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
            # Преобразуем в словарь
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
    """Конвертировать UTC время в локальное (Минск UTC+3)"""
    if not utc_dt:
        return ""
    
    try:
        if isinstance(utc_dt, str):
            # Убираем лишние пробелы и символы
            utc_dt = utc_dt.strip()
            
            # Если это только дата (без времени)
            if len(utc_dt) == 10 and '-' in utc_dt:
                return utc_dt
                
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
            return local_dt.strftime('%Y-%m-%d %H:%M:%S')
            
    except Exception as e:
        print(f"Ошибка конвертации времени {utc_dt}: {e}")
        if isinstance(utc_dt, str) and len(utc_dt) > 10:
            return utc_dt[:10]  # Возвращаем только дату при ошибке
        return str(utc_dt)

def log_action(seller_id, action_type, item_id=None, details="", ip_address=None):
    """Записать действие в лог"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        created_at_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
        INSERT INTO action_log (seller_id, action_type, item_id, details, ip_address, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ''', (seller_id, action_type, item_id, details, ip_address or request.remote_addr, created_at_utc))
        
        # Получаем информацию о продавце
        cursor.execute('SELECT username, display_name FROM sellers WHERE id = %s', (seller_id,))
        seller = cursor.fetchone()
        
        if seller:
            seller_name = seller[1] or seller[0]
            
            if action_type == 'logout':
                cursor.execute('DELETE FROM notifications WHERE seller_id = %s', (seller_id,))
                print(f"🗑️ Удалены уведомления для {seller_name}")
            elif action_type != 'login':
                # Получаем активных продавцов кроме текущего
                cursor.execute('''
                    SELECT DISTINCT seller_id FROM active_sessions 
                    WHERE seller_id != %s AND is_active = TRUE
                ''', (seller_id,))
                active_sellers = cursor.fetchall()
                
                # Создаем сообщение
                action_messages = {
                    'add_item': 'добавил новый товар',
                    'update_item': 'изменил статус товара',
                    'sale': 'продал товар',
                    'purchase': 'купил товар для магазина',
                    'personal': 'взял товар себе',
                    'error': 'ошибка'
                }
                
                action_msg = action_messages.get(action_type, action_type)
                message = f"{seller_name} {action_msg}"
                
                if item_id and details:
                    cursor.execute('SELECT name FROM items WHERE id = %s', (item_id,))
                    item = cursor.fetchone()
                    if item:
                        message += f": {item[0]}"
                    else:
                        message += f": {details[:50]}"
                elif details:
                    message += f": {details[:50]}"
                
                # Создаем уведомления
                for active_seller in active_sellers:
                    receiver_id = active_seller[0]
                    cursor.execute('''
                        SELECT 1 FROM active_sessions 
                        WHERE seller_id = %s AND is_active = TRUE
                    ''', (receiver_id,))
                    receiver_active = cursor.fetchone()
                    
                    if receiver_active:
                        cursor.execute('''
                        INSERT INTO notifications (seller_id, from_seller_id, message, item_id, action_type)
                        VALUES (%s, %s, %s, %s, %s)
                        ''', (receiver_id, seller_id, message, item_id, action_type))
        
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

def get_recent_actions(limit=10):
    """Получить последние действия"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT al.*, s.username, s.display_name
            FROM action_log al
            LEFT JOIN sellers s ON al.seller_id = s.id
            ORDER BY al.created_at DESC
            LIMIT %s
        ''', (limit,))
        
        actions = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        actions_list = []
        for action in actions:
            action_dict = dict(zip(columns, action))
            
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
                    else:
                        action_dict['created_at_local'] = created_str
                except Exception as e:
                    action_dict['created_at_local'] = str(action_dict['created_at'])
            else:
                action_dict['created_at_local'] = ''
            
            actions_list.append(action_dict)
        
        return actions_list
        
    except Exception as e:
        print(f"❌ Ошибка получения действий: {e}")
        return []
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
        
        # Удаляем сессии старше 8 часов
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
    """Получить список активных продавцов с правильным локальным временем"""
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
            
            # Конвертируем время входа из UTC в локальное
            if seller_dict['login_time']:
                login_time_utc = seller_dict['login_time']
                
                try:
                    # Преобразуем строку в datetime
                    if isinstance(login_time_utc, str):
                        try:
                            utc_time = datetime.strptime(login_time_utc, '%Y-%m-%d %H:%M:%S')
                        except:
                            try:
                                utc_time = datetime.strptime(login_time_utc, '%Y-%m-%d %H:%M:%S.%f')
                            except:
                                utc_time = datetime.now()
                    else:
                        utc_time = login_time_utc
                    
                    # Добавляем 3 часа для Минского времени (UTC+3)
                    local_time = utc_time + timedelta(hours=3)
                    
                    # Для отображения на странице покупателя - только время
                    seller_dict['login_time_local'] = local_time.strftime('%H:%M:%S')
                    seller_dict['login_time_short'] = local_time.strftime('%H:%M')
                    
                    # Полная дата и время для панели продавца
                    seller_dict['login_time_full'] = local_time.strftime('%d.%m.%Y %H:%M:%S')
                    
                except Exception as e:
                    print(f"Ошибка конвертации времени: {e}")
                    seller_dict['login_time_local'] = str(login_time_utc)[11:16] if login_time_utc else '??:??'
                    seller_dict['login_time_short'] = seller_dict['login_time_local']
                    seller_dict['login_time_full'] = str(login_time_utc)
            else:
                seller_dict['login_time_local'] = ''
                seller_dict['login_time_short'] = ''
                seller_dict['login_time_full'] = ''
            
            # Определяем активность
            if seller_dict['last_activity']:
                last_activity_utc = seller_dict['last_activity']
                if isinstance(last_activity_utc, str):
                    try:
                        last_activity_utc = datetime.strptime(last_activity_utc, '%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                minutes_since_activity = (now - last_activity_utc).total_seconds() / 60
                is_really_active = minutes_since_activity < 5
            else:
                is_really_active = False
            
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
        
        # УДАЛЯЕМ ВСЕ предыдущие сессии
        cursor.execute('DELETE FROM active_sessions WHERE seller_id = %s', (seller['id'],))
        deleted_count = cursor.rowcount
        
        if deleted_count > 0:
            print(f"🗑️ Удалено {deleted_count} старых сессий для {seller['username']}")
        
        # Создаем новую сессию
        session_token = secrets.token_hex(32)
        now_utc = datetime.utcnow()
        
        # Сохраняем время входа в UTC для консистентности
        login_time_utc = now_utc.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
        INSERT INTO active_sessions (seller_id, session_token, ip_address, user_agent, login_time, last_activity)
        VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            seller['id'], 
            session_token, 
            flask_request.remote_addr, 
            flask_request.user_agent.string[:200],
            login_time_utc,
            login_time_utc
        ))
        
        # Обновляем время последнего входа
        cursor.execute('UPDATE sellers SET last_login = %s WHERE id = %s',
                      (login_time_utc, seller['id']))
        
        conn.commit()
        
        # Сохраняем в сессии Flask
        session['seller_logged_in'] = True
        session['seller_id'] = seller['id']
        session['seller_username'] = seller['username']
        session['display_name'] = seller.get('display_name') or seller['username']
        session['session_token'] = session_token
        
        # Сохраняем время входа в UTC и локальное
        session['login_time_utc'] = login_time_utc
        
        # Конвертируем UTC в локальное время для отображения
        try:
            utc_time = datetime.strptime(login_time_utc, '%Y-%m-%d %H:%M:%S')
            local_time = utc_time + timedelta(hours=3)  # Минск UTC+3
            session['login_time_local'] = local_time.strftime('%H:%M:%S')
        except:
            session['login_time_local'] = login_time_utc[11:16]  # Берем только часы:минуты
        
        print(f"✅ Успешный вход: {seller['username']} в {login_time_utc} UTC")
        
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

# ==================== МАРШРУТЫ ====================

@app.context_processor
def inject_now():
    """Добавляет текущую дату во все шаблоны"""
    return {'now': datetime.now()}

@app.route('/')
def index():
    """Главная страница - перенаправляем сразу на покупателя"""
    return redirect(url_for('buyer'))

@app.route('/home')
def home():
    """Альтернативная главная страница"""
    return render_template('index.html')

@app.route('/buyer')
def buyer():
    """Страница для покупателей"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                id, 
                name, 
                sell_price, 
                manual_price,
                COALESCE(manual_price, sell_price) as display_price,
                status, 
                date_arrived
            FROM items 
            WHERE status IN ('в наличии', 'в пути')
            ORDER BY 
                CASE status 
                    WHEN 'в наличии' THEN 1
                    WHEN 'в пути' THEN 2
                    ELSE 3
                END,
                date_arrived DESC,
                id DESC
        ''')
        
        items = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        items_list = []
        for item_tuple in items:
            item_dict = dict(zip(columns, item_tuple))
            # Для отображения используем manual_price если он есть, иначе sell_price
            item_dict['display_price'] = item_dict['manual_price'] or item_dict['sell_price']
            items_list.append(item_dict)
        
        in_stock = [item for item in items_list if item['status'] == 'в наличии']
        in_transit = [item for item in items_list if item['status'] == 'в пути']
        
        # Получаем активных продавцов
        active_sellers = get_active_sellers()
        really_active_sellers = [s for s in active_sellers if s.get('is_really_active', False)]
        
        return render_template('buyer.html',
                             in_stock=in_stock,
                             in_transit=in_transit,
                             total=len(items_list),
                             active_sellers=really_active_sellers)
                             
    except Exception as e:
        print(f"❌ Ошибка в buyer: {e}")
        return render_template('buyer.html',
                             in_stock=[],
                             in_transit=[],
                             total=0,
                             active_sellers=[])
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
        
        cursor.execute('''
            SELECT * FROM active_sessions 
            WHERE seller_id = %s AND is_active = TRUE
        ''', (seller['id'],))
        
        old_session = cursor.fetchone()
        
        if old_session:
            log_action(seller['id'], 'force_logout', 
                      details=f'Принудительно завершена сессия')
            print(f"🔒 Принудительно завершаем сессию для {pending_login['username']}")
        
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
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем валидность сессии
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
        
        # Обновляем время активности
        cursor.execute('''
        UPDATE active_sessions 
        SET last_activity = %s
        WHERE session_token = %s AND seller_id = %s
        ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), session_token, seller_id))
        
        # Получаем товары
        cursor.execute('''
            SELECT * FROM items 
            ORDER BY 
                CASE status 
                    WHEN 'в наличии' THEN 1
                    WHEN 'в пути' THEN 2
                    WHEN 'продано' THEN 3
                    WHEN 'взял себе' THEN 4
                    ELSE 5
                END,
                id DESC
        ''')
        
        items = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        items_list = []
        for item_tuple in items:
            items_list.append(dict(zip(columns, item_tuple)))
        
        # Статистика
        stats = {
            'total': len(items_list),
            'in_stock': len([i for i in items_list if i['status'] == 'в наличии']),
            'sold': len([i for i in items_list if i['status'] == 'продано']),
            'in_transit': len([i for i in items_list if i['status'] == 'в пути']),
            'personal': len([i for i in items_list if i['status'] == 'взял себе']),
        }
        
        conn.commit()
        
        # Последние действия
        recent_actions = get_recent_actions(limit=10)
        
        # Активные продавцы
        active_sellers_list = get_active_sellers()
        
        # Количество активных
        active_count = len([s for s in active_sellers_list if s.get('is_really_active', False)])
        
        return render_template('seller_dashboard.html',
                             items=items_list,
                             stats=stats,
                             recent_actions=recent_actions,
                             active_sellers=active_sellers_list,
                             active_count=active_count,
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

@app.route('/seller/add', methods=['POST'])
def add_item():
    """Добавить товар (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO items (name, cost_price, sell_price, status, date_arrived)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (
            data['name'],
            float(data['cost_price']),
            float(data['sell_price']),
            data['status'],
            datetime.now().strftime('%Y-%m-%d')
        ))
        
        item_id = cursor.fetchone()[0]
        
        if data['status'] != 'в пути':
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
        
        log_action(session['seller_id'], 'add_item', item_id, 
                  f'Добавлен товар: {data["name"]}')
        
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

@app.route('/seller/item_info/<int:item_id>')
def get_item_info(item_id):
    """Получить информацию о товаре"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, status FROM items WHERE id = %s', (item_id,))
        item_tuple = cursor.fetchone()
        
        if not item_tuple:
            return jsonify({'success': False, 'error': 'Товар не найден'})
        
        item = {
            'id': item_tuple[0],
            'name': item_tuple[1],
            'status': item_tuple[2]
        }
        
        return jsonify({'success': True, 'item': item})
        
    except Exception as e:
        print(f"❌ Ошибка получения информации о товаре: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/update/<int:item_id>', methods=['POST'])
def update_item(item_id):
    """Обновить статус товара и проверяем статус поставки"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        new_status = data['status']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM items WHERE id = %s', (item_id,))
        item_tuple = cursor.fetchone()
        
        if not item_tuple:
            return jsonify({'error': 'Товар не найден'}), 404
        
        columns = [desc[0] for desc in cursor.description]
        item = dict(zip(columns, item_tuple))
        
        old_status = item['status']
        
        # Обновляем статус товара
        if new_status == 'продано':
            cursor.execute('UPDATE items SET status = %s, date_sold = %s WHERE id = %s',
                          (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        elif new_status == 'взял себе':
            cursor.execute('UPDATE items SET status = %s, date_taken = %s WHERE id = %s',
                          (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        else:
            cursor.execute('UPDATE items SET status = %s WHERE id = %s', (new_status, item_id))
        
        # Добавляем транзакцию продажи
        if old_status != 'продано' and new_status == 'продано':
            cursor.execute('''
            INSERT INTO transactions (date, type, item_id, amount, note)
            VALUES (%s, %s, %s, %s, %s)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                'sale',
                item_id,
                float(item['sell_price']),
                f'Продажа {item["name"]}'
            ))
        
        # Проверяем и обновляем статус поставки
        if item.get('shipment_id'):
            # Проверяем статусы всех товаров в поставке
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'продано' THEN 1 ELSE 0 END) as sold_count,
                    SUM(CASE WHEN status = 'взял себе' THEN 1 ELSE 0 END) as taken_count
                FROM items 
                WHERE shipment_id = %s
            ''', (item['shipment_id'],))
            
            stats = cursor.fetchone()
            total_items = stats[0]
            sold_count = stats[1] or 0
            taken_count = stats[2] or 0
            
            # Получаем текущий статус поставки
            cursor.execute('SELECT status FROM shipments WHERE id = %s', (item['shipment_id'],))
            shipment_status = cursor.fetchone()
            
            if shipment_status:
                shipment_status = shipment_status[0]
                
                # Если все товары проданы или взяты себе
                if (sold_count + taken_count) == total_items:
                    # Все товары проданы - поставка продана
                    if sold_count == total_items:
                        cursor.execute('UPDATE shipments SET status = %s WHERE id = %s', 
                                      ('продано', item['shipment_id']))
                    # Все товары взяты себе - поставка завершена
                    elif taken_count == total_items:
                        cursor.execute('UPDATE shipments SET status = %s WHERE id = %s', 
                                      ('завершена', item['shipment_id']))
                    # Смешанный статус - поставка частично продана
                    else:
                        cursor.execute('UPDATE shipments SET status = %s WHERE id = %s', 
                                      ('частично продана', item['shipment_id']))
                # Если есть хотя бы один проданный товар, но не все
                elif sold_count > 0:
                    cursor.execute('UPDATE shipments SET status = %s WHERE id = %s', 
                                  ('частично продана', item['shipment_id']))
        
        conn.commit()
        
        log_action(session['seller_id'], 'update_item', item_id, 
                  f'Статус изменен: {old_status} -> {new_status}')
        
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

@app.route('/seller/notifications')
def get_notifications():
    """Получить непрочитанные уведомления"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT n.*, s.username as from_username, s.display_name as from_display_name
            FROM notifications n
            LEFT JOIN sellers s ON n.from_seller_id = s.id
            WHERE n.seller_id = %s AND n.is_read = FALSE
            ORDER BY n.created_at DESC
            LIMIT 20
        ''', (session['seller_id'],))
        
        notifications = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        notifications_list = []
        for notif_tuple in notifications:
            notifications_list.append(dict(zip(columns, notif_tuple)))
        
        if notifications_list:
            cursor.execute('UPDATE notifications SET is_read = TRUE WHERE seller_id = %s AND is_read = FALSE', 
                          (session['seller_id'],))
        
        conn.commit()
        return jsonify({'notifications': notifications_list})
        
    except Exception as e:
        print(f"❌ Ошибка получения уведомлений: {e}")
        return jsonify({'notifications': []})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Добавляем в app.py функцию для получения статусов товаров
@app.route('/seller/item_statuses')
def get_item_statuses():
    """Получить список доступных статусов для товаров"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    statuses = [
        {'value': 'в наличии', 'label': 'В наличии'},
        {'value': 'продано', 'label': 'Продано'},
        {'value': 'зарезервировано', 'label': 'Зарезервировано'},
        {'value': 'взял себе', 'label': 'Взял себе'},
        {'value': 'в пути', 'label': 'В пути'},
    ]
    
    return jsonify({'statuses': statuses})

@app.route('/seller/notification_count')
def notification_count():
    """Количество непрочитанных уведомлений"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE seller_id = %s AND is_read = FALSE', 
                      (session['seller_id'],))
        
        count = cursor.fetchone()[0]
        return jsonify({'count': count})
        
    except Exception as e:
        print(f"❌ Ошибка подсчета уведомлений: {e}")
        return jsonify({'count': 0})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/mark_all_read', methods=['POST'])
def mark_all_read():
    """Пометить все уведомления как прочитанные"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE notifications SET is_read = TRUE WHERE seller_id = %s', 
                      (session['seller_id'],))
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка пометки уведомлений: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/active_sellers')
def get_active_sellers_list():
    """Получить список активных продавцов"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    active_sellers = get_active_sellers()
    return jsonify({'active_sellers': active_sellers})

@app.route('/seller/active_sellers_count_public')
def active_sellers_count_public():
    """Количество активных продавцов (публичный доступ)"""
    clear_old_sessions()
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        five_minutes_ago = (datetime.utcnow() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            SELECT COUNT(DISTINCT seller_id) as cnt
            FROM active_sessions 
            WHERE is_active = TRUE AND last_activity > %s
        ''', (five_minutes_ago,))
        
        count = cursor.fetchone()[0]
        return jsonify({'count': count})
        
    except Exception as e:
        print(f"❌ Ошибка подсчета продавцов: {e}")
        return jsonify({'count': 0})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/active_sellers_list_public')
def active_sellers_list_public():
    """Список активных продавцов (публичный доступ) с правильным временем"""
    clear_old_sessions()
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        five_minutes_ago = (datetime.utcnow() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            SELECT s.username, s.display_name, a.login_time
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.is_active = TRUE AND a.last_activity > %s
            ORDER BY a.last_activity DESC
            LIMIT 10
        ''', (five_minutes_ago,))
        
        sellers = cursor.fetchall()
        
        sellers_list = []
        for seller in sellers:
            try:
                login_time = seller[2]
                if login_time:
                    # Преобразуем UTC в локальное время
                    if isinstance(login_time, str):
                        try:
                            utc_time = datetime.strptime(login_time, '%Y-%m-%d %H:%M:%S')
                        except:
                            utc_time = datetime.now()
                    else:
                        utc_time = login_time
                    
                    # Добавляем 3 часа для Минска (UTC+3)
                    local_time = utc_time + timedelta(hours=3)
                    login_time_short = local_time.strftime('%H:%M')
                else:
                    login_time_short = '??:??'
            except:
                login_time_short = seller[2][11:16] if seller[2] and len(str(seller[2])) > 16 else '??:??'
            
            sellers_list.append({
                'username': seller[0],
                'display_name': seller[1] or seller[0],
                'login_time_short': login_time_short
            })
        
        return jsonify({'sellers': sellers_list})
        
    except Exception as e:
        print(f"❌ Ошибка списка продавцов: {e}")
        return jsonify({'sellers': []})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/check_session')
def check_session():
    """Проверка валидности сессии"""
    if not session.get('seller_logged_in') or not session.get('session_token'):
        return jsonify({'valid': False, 'reason': 'no_session'}), 401
    
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
        
        if current_session:
            return jsonify({'valid': True})
        else:
            session.clear()
            return jsonify({'valid': False, 'reason': 'session_replaced'}), 401
            
    except Exception as e:
        print(f"❌ Ошибка проверки сессии: {e}")
        return jsonify({'valid': False, 'reason': 'error'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/shipments/<int:shipment_id>')
def get_shipment_info(shipment_id):
    """Получить информацию о конкретной поставке"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM shipments 
            WHERE id = %s
        ''', (shipment_id,))
        
        shipment_tuple = cursor.fetchone()
        
        if not shipment_tuple:
            return jsonify({'success': False, 'error': 'Поставка не найдена'})
        
        columns = [desc[0] for desc in cursor.description]
        shipment_dict = dict(zip(columns, shipment_tuple))
        
        return jsonify({'success': True, 'shipments': [shipment_dict]})
        
    except Exception as e:
        print(f"❌ Ошибка получения информации о поставке: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/buyer/active_sellers')
def buyer_active_sellers():
    """API для получения активных продавцов с правильным временем"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Берем продавцов активных в последние 10 минут
        ten_minutes_ago = (datetime.utcnow() - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            SELECT s.id, s.username, s.display_name, a.login_time, a.last_activity
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.is_active = TRUE 
            AND a.last_activity > %s
            ORDER BY a.last_activity DESC
        ''', (ten_minutes_ago,))
        
        sellers = cursor.fetchall()
        
        simplified_sellers = []
        for seller in sellers:
            try:
                login_time = seller[3]  # login_time в UTC
                if login_time:
                    # Преобразуем UTC время в локальное (Минск UTC+3)
                    if isinstance(login_time, str):
                        try:
                            # Пробуем разные форматы
                            formats = [
                                '%Y-%m-%d %H:%M:%S',
                                '%Y-%m-%d %H:%M:%S.%f',
                                '%H:%M:%S'
                            ]
                            for fmt in formats:
                                try:
                                    utc_time = datetime.strptime(login_time, fmt)
                                    break
                                except:
                                    continue
                            else:
                                utc_time = datetime.now()
                        except:
                            utc_time = datetime.now()
                    else:
                        utc_time = login_time
                    
                    # Добавляем 3 часа для Минского времени
                    local_time = utc_time + timedelta(hours=3)
                    login_time_short = local_time.strftime('%H:%M')
                else:
                    login_time_short = '??:??'
            except Exception as e:
                print(f"Ошибка преобразования времени: {e}")
                login_time_short = seller[3][11:16] if seller[3] and len(str(seller[3])) > 16 else '??:??'
            
            simplified_sellers.append({
                'id': seller[0],
                'username': seller[1],
                'display_name': seller[2] or seller[1],
                'login_time_short': login_time_short,
                'login_time_full': login_time_short
            })
        
        return jsonify({'active_sellers': simplified_sellers})
        
    except Exception as e:
        print(f"❌ Ошибка получения продавцов: {e}")
        return jsonify({'active_sellers': []})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== МАРШРУТЫ ДЛЯ ПОСТАВОК (PostgreSQL версия) ====================

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
        
        cursor.execute('''
            SELECT s.*, 
                   CASE 
                       WHEN s.shipment_number IS NOT NULL AND s.shipment_number != '' 
                       THEN s.shipment_number
                       ELSE 'SHIP-' || LPAD(s.id::text, 3, '0')
                   END as display_number
            FROM shipments s 
            ORDER BY s.order_date DESC, s.id DESC
        ''')
        
        shipments = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        shipments_list = []
        for shipment_tuple in shipments:
            shipment_dict = dict(zip(columns, shipment_tuple))
            
            # Используем display_number вместо shipment_number для отображения
            if not shipment_dict.get('shipment_number') or shipment_dict['shipment_number'] == '':
                shipment_dict['shipment_number'] = f"SHIP-{shipment_dict['id']:03d}"
            
            shipments_list.append(shipment_dict)
        
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
        
        # Получаем последний номер
        cursor.execute('SELECT id FROM shipments ORDER BY id DESC LIMIT 1')
        last_shipment = cursor.fetchone()
        
        if last_shipment:
            new_num = last_shipment[0] + 1
        else:
            new_num = 1
        
        shipment_number = f"SHIP-{new_num:03d}"
        
        # УБИРАЕМ delivery_cost из создания поставки
        cursor.execute('''
        INSERT INTO shipments (shipment_number, order_date, status)
        VALUES (%s, %s, %s) RETURNING id
        ''', (
            shipment_number,
            data['order_date'],
            'в пути'  # Все новые поставки по умолчанию "в пути"
        ))
        
        shipment_id = cursor.fetchone()[0]
        
        conn.commit()
        
        log_action(session['seller_id'], 'create_shipment', 
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
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка создания поставки: {str(e)}')
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
        # Проверяем Content-Type
        if not request.is_json:
            return jsonify({'error': 'Content-Type должен быть application/json'}), 400
            
        data = request.get_json()
        
        # Проверяем обязательные поля
        if not data or 'items' not in data:
            return jsonify({'error': 'Не указаны товары'}), 400
            
        items = data['items']
        status = data.get('status', 'в пути')
        
        if not isinstance(items, list) or len(items) == 0:
            return jsonify({'error': 'Товары должны быть списком'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существование поставки
        cursor.execute('SELECT id, status FROM shipments WHERE id = %s', (shipment_id,))
        shipment_tuple = cursor.fetchone()
        
        if not shipment_tuple:
            return jsonify({'error': 'Поставка не найдена'}), 404
        
        # Вставляем товары
        added_items = []
        for item_data in items:
            # Проверяем обязательные поля товара
            if 'name' not in item_data or not item_data['name']:
                continue
                
            cost_price = float(item_data.get('cost_price', 0))
            sell_price = float(item_data.get('sell_price', 0))
            
            cursor.execute('''
            INSERT INTO items (name, cost_price, sell_price, status, shipment_id, date_arrived)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            ''', (
                item_data['name'].strip(),
                cost_price,
                sell_price,
                status,
                shipment_id,
                datetime.now().strftime('%Y-%m-%d')
            ))
            
            item_id = cursor.fetchone()[0]
            added_items.append({
                'id': item_id,
                'name': item_data['name']
            })
        
        # Обновляем счетчик товаров в поставке
        cursor.execute('''
        UPDATE shipments 
        SET total_items = total_items + %s, updated_at = %s
        WHERE id = %s
        ''', (len(added_items), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        conn.commit()
        
        log_action(session['seller_id'], 'add_items_to_shipment', 
                  details=f'Добавлено {len(added_items)} товаров в поставку #{shipment_id}')
        
        return jsonify({
            'success': True, 
            'added_count': len(added_items),
            'items': added_items
        })
        
    except Exception as e:
        print(f"❌ Ошибка добавления товаров: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
# ПЕРЕИМЕНОВАЛИ эту функцию, чтобы избежать конфликта имен
@app.route('/seller/shipments/<int:shipment_id>/update_status_with_delivery', methods=['POST'])
def update_shipment_status_with_delivery(shipment_id):
    """Обновить статус поставки с учетом стоимости доставки"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        data = request.get_json()
        new_status = data['status']
        received_date = data.get('received_date', datetime.now().strftime('%Y-%m-%d'))
        delivery_cost = data.get('delivery_cost', 0)  # Получаем стоимость доставки
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Обновляем статус поставки и добавляем стоимость доставки
        cursor.execute('''
        UPDATE shipments 
        SET status = %s, received_date = %s, delivery_cost = %s, updated_at = %s
        WHERE id = %s
        RETURNING shipment_number
        ''', (new_status, received_date, float(delivery_cost) if delivery_cost else 0,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        shipment = cursor.fetchone()
        
        # Обновляем статус товаров
        cursor.execute('''
        UPDATE items 
        SET status = %s, date_arrived = %s
        WHERE shipment_id = %s AND status != 'продано' AND status != 'взял себе'
        ''', (new_status, received_date, shipment_id))
        
        # Если статус меняется на "в наличии", добавляем транзакции
        if new_status == 'в наличии':
            # 1. Получаем все товары из поставки
            cursor.execute('''
            SELECT id, name, cost_price FROM items 
            WHERE shipment_id = %s AND status = 'в наличии'
            ''', (shipment_id,))
            
            items = cursor.fetchall()
            
            total_purchase_cost = 0
            
            for item in items:
                cursor.execute('''
                SELECT tx_id FROM transactions 
                WHERE item_id = %s AND type = 'purchase'
                ''', (item[0],))
                
                existing_tx = cursor.fetchone()
                
                if not existing_tx:
                    # Добавляем транзакцию покупки товара
                    cursor.execute('''
                    INSERT INTO transactions (date, type, item_id, amount, note)
                    VALUES (%s, %s, %s, %s, %s)
                    ''', (
                        received_date,
                        'purchase',
                        item[0],
                        -float(item[2]),  # Отрицательная сумма - расход
                        f'Покупка {item[1]}'
                    ))
                    total_purchase_cost += float(item[2])
            
            # 2. Добавляем отдельную транзакцию для доставки
            if delivery_cost and float(delivery_cost) > 0:
                cursor.execute('''
                INSERT INTO transactions (date, type, amount, note)
                VALUES (%s, %s, %s, %s)
                ''', (
                    received_date,
                    'delivery',
                    -float(delivery_cost),  # Отрицательная сумма - расход
                    f'Доставка поставки {shipment[0] if shipment else shipment_id}'
                ))
        
        conn.commit()
        
        log_action(session['seller_id'], 'update_shipment_status', 
                  details=f'Статус поставки #{shipment_id} изменен на "{new_status}" с доставкой {delivery_cost} BYN')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка обновления статуса: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка обновления статуса поставки: {str(e)}')
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
        
        # Сначала получаем текущую цену
        cursor.execute('SELECT sell_price FROM items WHERE id = %s', (item_id,))
        current_price = cursor.fetchone()
        
        if not current_price:
            return jsonify({'error': 'Товар не найден'}), 404
        
        # Обновляем manual_price, сохраняя оригинальную цену в sell_price
        cursor.execute('''
        UPDATE items 
        SET manual_price = %s
        WHERE id = %s
        ''', (new_price, item_id))
        
        conn.commit()
        
        log_action(session['seller_id'], 'update_item_price', item_id,
                  f'Цена изменена с {current_price[0]} на {new_price} BYN')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка обновления цены: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка обновления цены: {str(e)}')
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
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка удаления товара: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/seller/items/shipment/<int:shipment_id>')
def get_items_by_shipment(shipment_id):
    """Получить товары по ID поставки"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM items 
            WHERE shipment_id = %s
            ORDER BY id
        ''', (shipment_id,))
        
        items = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        items_list = []
        for item_tuple in items:
            items_list.append(dict(zip(columns, item_tuple)))
        
        return jsonify({'items': items_list})
        
    except Exception as e:
        print(f"❌ Ошибка получения товаров поставки: {e}")
        return jsonify({'items': []})
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

@app.route('/seller/shipments/<int:shipment_id>/delete', methods=['POST'])
def delete_shipment(shipment_id):
    """Удалить поставку со всеми товарами"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем информацию о поставке
        cursor.execute('SELECT shipment_number, total_items FROM shipments WHERE id = %s', (shipment_id,))
        shipment = cursor.fetchone()
        
        if not shipment:
            return jsonify({'error': 'Поставка не найдена'}), 404
        
        shipment_number = shipment[0]
        total_items = shipment[1]
        
        # Удаляем транзакции связанные с товарами из этой поставки
        cursor.execute('''
            DELETE FROM transactions 
            WHERE item_id IN (
                SELECT id FROM items WHERE shipment_id = %s
            )
        ''', (shipment_id,))
        
        # Удаляем товары из этой поставки
        cursor.execute('DELETE FROM items WHERE shipment_id = %s', (shipment_id,))
        
        # Удаляем уведомления связанные с этими товарами
        cursor.execute('''
            DELETE FROM notifications 
            WHERE item_id IN (
                SELECT id FROM items WHERE shipment_id = %s
            )
        ''', (shipment_id,))
        
        # Удаляем саму поставку
        cursor.execute('DELETE FROM shipments WHERE id = %s', (shipment_id,))
        
        conn.commit()
        
        log_action(session['seller_id'], 'delete_shipment', 
                  details=f'Удалена поставка {shipment_number} с {total_items} товарами')
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"❌ Ошибка удаления поставки: {e}")
        if conn:
            conn.rollback()
        log_action(session.get('seller_id'), 'error', 
                  details=f'Ошибка удаления поставки: {str(e)}')
        return jsonify({'error': str(e)}), 400
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ПАНЕЛЬ ОТЛАДКИ И АДМИНИСТРИРОВАНИЯ ====================

@app.route('/seller/debug', methods=['GET', 'POST'])
def debug_panel():
    """Скрытая панель отладки только для SlavchikSV"""
    if not session.get('seller_logged_in'):
        return redirect(url_for('seller_login'))
    
    if session.get('seller_username') != 'SlavchikSV':
        flash('Доступ запрещен. Только для администратора.', 'danger')
        return redirect(url_for('seller_dashboard'))
    
    conn = None
    cursor = None
    
    if request.method == 'POST':
        action = request.form.get('action')
        password = request.form.get('password')
        
        # Проверяем пароль администратора
        admin = get_seller_by_username('SlavchikSV')
        if not admin or not bcrypt.check_password_hash(admin['password_hash'], password):
            flash('Неверный пароль администратора', 'danger')
            return redirect(url_for('debug_panel'))
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if action == 'clear_logs':
                cursor.execute('DELETE FROM action_log')
                cursor.execute('DELETE FROM notifications')
                cursor.execute("VACUUM")
                flash('✅ Логи и уведомления успешно очищены!', 'success')
                
            elif action == 'clear_all_data':
                # Сохраняем пользователей
                cursor.execute('SELECT * FROM sellers')
                sellers_backup = cursor.fetchall()
                
                # Удаляем все данные кроме пользователей
                tables = ['items', 'transactions', 'action_log', 'notifications', 'shipments', 'active_sessions']
                for table in tables:
                    cursor.execute(f'DELETE FROM {table}')
                
                # Обнуляем автоинкременты
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('items', 'transactions', 'action_log', 'notifications', 'shipments', 'active_sessions')")
                
                cursor.execute("VACUUM")
                flash('✅ Все данные (кроме пользователей) успешно очищены! База данных как новая.', 'success')
                
            elif action == 'clear_shipments':
                cursor.execute('DELETE FROM shipments')
                cursor.execute('UPDATE items SET shipment_id = NULL')
                cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'shipments'")
                cursor.execute("VACUUM")
                flash('✅ Все поставки успешно удалены!', 'success')
                
            elif action == 'reset_counters':
                # Сброс счетчиков автоинкремента
                cursor.execute("DELETE FROM sqlite_sequence")
                cursor.execute("VACUUM")
                flash('✅ Счетчики автоинкремента сброшены!', 'success')
                
            elif action == 'export_database':
                # Экспорт базы данных в JSON
                from datetime import datetime
                import json
                
                export_data = {
                    'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'tables': {}
                }
                
                # Экспортируем все таблицы
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                
                for table in tables:
                    table_name = table[0]
                    cursor.execute(f'SELECT * FROM {table_name}')
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    
                    table_data = []
                    for row in rows:
                        table_data.append(dict(zip(columns, row)))
                    
                    export_data['tables'][table_name] = table_data
                
                # Сохраняем в файл
                export_filename = f'db_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                with open(export_filename, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                
                flash(f'✅ База данных экспортирована в файл: {export_filename}', 'success')
                
            elif action == 'optimize_database':
                cursor.execute("VACUUM")
                cursor.execute("ANALYZE")
                flash('✅ База данных оптимизирована и сжата!', 'success')
                
            elif action == 'show_system_info':
                # Собираем системную информацию
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                
                info = []
                for table in tables:
                    cursor.execute(f'SELECT COUNT(*) FROM {table[0]}')
                    count = cursor.fetchone()[0]
                    info.append(f"{table[0]}: {count} записей")
                
                session['system_info'] = info
                flash('✅ Системная информация собрана', 'success')
            
            conn.commit()
            
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f'❌ Ошибка выполнения операции: {str(e)}', 'danger')
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    # Получаем статистику базы данных
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {}
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) FROM {table[0]}')
        count = cursor.fetchone()[0]
        stats[table[0]] = count
    
    cursor.close()
    conn.close()
    
    system_info = session.pop('system_info', [])
    
    return render_template('debug_panel.html', stats=stats, system_info=system_info)

@app.route('/seller/debug/api/statistics')
def debug_statistics():
    """API для получения статистики базы данных"""
    if not session.get('seller_logged_in') or session.get('seller_username') != 'SlavchikSV':
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        statistics = {}
        for table in tables:
            cursor.execute(f'SELECT COUNT(*) FROM {table[0]}')
            count = cursor.fetchone()[0]
            
            # Для больших таблиц получаем дополнительную информацию
            if table[0] in ['items', 'action_log', 'transactions']:
                cursor.execute(f'''
                    SELECT 
                        MIN(created_at) as oldest,
                        MAX(created_at) as newest
                    FROM {table[0]}
                    WHERE created_at IS NOT NULL
                ''')
                date_info = cursor.fetchone()
                statistics[table[0]] = {
                    'count': count,
                    'oldest': date_info[0] if date_info[0] else 'N/A',
                    'newest': date_info[1] if date_info[1] else 'N/A'
                }
            else:
                statistics[table[0]] = {'count': count}
        
        # Размер базы данных
        cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
        db_size = cursor.fetchone()[0]
        
        statistics['database_size'] = {
            'bytes': db_size,
            'mb': round(db_size / (1024 * 1024), 2)
        }
        
        return jsonify({'success': True, 'statistics': statistics})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ЗАПУСК СЕРВЕРА ====================

if __name__ == '__main__':
    # Очищаем старые сессии при запуске
    clear_old_sessions()
    
    # Запускаем сервер
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

















