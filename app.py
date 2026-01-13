import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash, g
from flask_bcrypt import Bcrypt
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
import secrets
import traceback

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this-in-production')
bcrypt = Bcrypt(app)

# ==================== БАЗА ДАННЫХ PostgreSQL ====================
def get_db():
    """Подключение к PostgreSQL"""
    if 'db' not in g:
        DATABASE_URL = os.environ.get('DATABASE_URL')
        
        if not DATABASE_URL:
            print("⚠️ DATABASE_URL не найден, использую SQLite для локальной разработки")
            import sqlite3
            conn = sqlite3.connect('shop.db', check_same_thread=False)
            conn.row_factory = sqlite3.Row
            g.db = conn
        else:
            print(f"🔗 Подключение к PostgreSQL")
            conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            conn.cursor_factory = DictCursor
            g.db = conn
    
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Закрыть соединение с БД"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Инициализация таблиц в PostgreSQL"""
    print("🔄 Инициализация базы данных PostgreSQL...")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Таблица товаров
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            cost_price REAL NOT NULL,
            sell_price REAL NOT NULL,
            manual_price REAL,
            status TEXT NOT NULL,
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
            amount REAL,
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
            delivery_cost REAL DEFAULT 0,
            status TEXT DEFAULT 'в пути',
            total_items INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Добавляем стандартных продавцов
        default_sellers = [
            ('SlavchikSV', 'sv280606', 'Администратор', 'admin'),
            ('mkozlov', '020988mama', 'Главный администратор', 'admin'),
        ]
        
        for username, password, display, role in default_sellers:
            cursor.execute('SELECT id FROM sellers WHERE username = %s', (username,))
            if not cursor.fetchone():
                password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
                cursor.execute('''
                INSERT INTO sellers (username, password_hash, display_name, role)
                VALUES (%s, %s, %s, %s)
                ''', (username, password_hash, display, role))
        
        conn.commit()
        print("✅ PostgreSQL база данных инициализирована")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации PostgreSQL: {e}")
        conn.rollback()
    finally:
        cursor.close()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def execute_query(query, params=(), fetchone=False, fetchall=False):
    """Универсальная функция для выполнения SQL запросов"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(query, params)
        
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        else:
            conn.commit()
            result = cursor.rowcount
        
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()

def get_seller_by_username(username):
    """Найти продавца по логину"""
    result = execute_query(
        'SELECT * FROM sellers WHERE username = %s', 
        (username,), 
        fetchone=True
    )
    return result

def get_seller_by_id(seller_id):
    """Найти продавца по ID"""
    result = execute_query(
        'SELECT * FROM sellers WHERE id = %s', 
        (seller_id,), 
        fetchone=True
    )
    return result

def utc_to_local(utc_dt, format_only_time=False):
    """Конвертировать UTC время в локальное"""
    if not utc_dt:
        return ""
    
    try:
        if isinstance(utc_dt, str):
            formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%H:%M:%S', '%Y-%m-%d']
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
            return local_dt.strftime('%H:%M:%S')
            
    except Exception as e:
        if isinstance(utc_dt, str) and len(utc_dt) > 10:
            return utc_dt[11:16]
        return str(utc_dt)

def log_action(seller_id, action_type, item_id=None, details="", ip_address=None):
    """Записать действие в лог"""
    try:
        execute_query('''
        INSERT INTO action_log (seller_id, action_type, item_id, details, ip_address, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ''', (seller_id, action_type, item_id, details, ip_address or request.remote_addr, datetime.utcnow()))
        
        if action_type not in ['login', 'logout']:
            seller = get_seller_by_id(seller_id)
            if seller:
                seller_name = seller['display_name'] or seller['username']
                action_messages = {
                    'add_item': 'добавил новый товар',
                    'update_item': 'изменил статус товара',
                    'sale': 'продал товар',
                    'purchase': 'купил товар для магазина',
                    'personal': 'взял товар себе'
                }
                
                action_msg = action_messages.get(action_type, action_type)
                message = f"{seller_name} {action_msg}"
                
                if details:
                    message += f": {details[:50]}"
                
                # Получаем всех активных продавцов кроме текущего
                active_sellers = execute_query('''
                    SELECT DISTINCT seller_id FROM active_sessions 
                    WHERE seller_id != %s AND is_active = TRUE
                ''', (seller_id,), fetchall=True)
                
                for active_seller in active_sellers:
                    execute_query('''
                    INSERT INTO notifications (seller_id, from_seller_id, message, item_id, action_type)
                    VALUES (%s, %s, %s, %s, %s)
                    ''', (active_seller['seller_id'], seller_id, message, item_id, action_type))
        
        print(f"📝 Действие записано: {seller_id} - {action_type}")
        
    except Exception as e:
        print(f"❌ Ошибка при записи лога: {e}")

def get_recent_actions(limit=10):
    """Получить последние действия"""
    actions = execute_query('''
        SELECT al.*, s.username, s.display_name
        FROM action_log al
        LEFT JOIN sellers s ON al.seller_id = s.id
        ORDER BY al.created_at DESC
        LIMIT %s
    ''', (limit,), fetchall=True)
    
    actions_list = []
    for action in actions:
        action_dict = dict(action)
        
        if action_dict['created_at']:
            try:
                utc_time = action_dict['created_at']
                if isinstance(utc_time, str):
                    utc_time = datetime.strptime(utc_time, '%Y-%m-%d %H:%M:%S')
                
                local_time = utc_time + timedelta(hours=3)
                action_dict['created_at_local'] = local_time.strftime('%d.%m.%Y %H:%M:%S')
            except:
                action_dict['created_at_local'] = str(action_dict['created_at'])
        else:
            action_dict['created_at_local'] = ''
        
        actions_list.append(action_dict)
    
    return actions_list

def clear_old_sessions():
    """Очистка старых неактивных сессий"""
    try:
        deleted = execute_query('''
        DELETE FROM active_sessions 
        WHERE last_activity < NOW() - INTERVAL '8 hours'
        ''')
        if deleted > 0:
            print(f"🧹 Очищено {deleted} старых сессий")
    except Exception as e:
        print(f"⚠️ Ошибка при очистке сессий: {e}")

def get_active_sellers():
    """Получить список активных продавцов"""
    sellers = execute_query('''
        SELECT s.id, s.username, s.display_name, 
               a.login_time, a.last_activity, a.session_token
        FROM active_sessions a
        JOIN sellers s ON a.seller_id = s.id
        WHERE a.is_active = TRUE
        ORDER BY a.last_activity DESC
    ''', fetchall=True)
    
    result = []
    now = datetime.utcnow()
    
    for seller in sellers:
        seller_dict = dict(seller)
        
        # Конвертируем время
        login_time = seller_dict['login_time']
        if isinstance(login_time, str):
            try:
                login_time_utc = datetime.strptime(login_time, '%Y-%m-%d %H:%M:%S')
                seller_dict['login_time_local'] = utc_to_local(login_time_utc)
                seller_dict['login_time_short'] = seller_dict['login_time_local'][:5]
            except:
                seller_dict['login_time_local'] = login_time
                seller_dict['login_time_short'] = login_time[11:16] if login_time and len(login_time) > 16 else '??:??'
        
        # Определяем активность
        last_activity = seller_dict['last_activity']
        if isinstance(last_activity, str):
            try:
                last_activity_utc = datetime.strptime(last_activity, '%Y-%m-%d %H:%M:%S')
                minutes_since_activity = (now - last_activity_utc).total_seconds() / 60
            except:
                minutes_since_activity = 999
        else:
            minutes_since_activity = 999
        
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
    cursor = conn.cursor()
    
    try:
        # Удаляем старые сессии
        cursor.execute('DELETE FROM active_sessions WHERE seller_id = %s', (seller['id'],))
        
        # Создаем новую сессию
        session_token = secrets.token_hex(32)
        now_utc = datetime.utcnow()
        
        cursor.execute('''
        INSERT INTO active_sessions (seller_id, session_token, ip_address, user_agent, login_time, last_activity)
        VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            seller['id'], 
            session_token, 
            flask_request.remote_addr, 
            flask_request.user_agent.string[:200],
            now_utc,
            now_utc
        ))
        
        # Обновляем время последнего входа
        cursor.execute('UPDATE sellers SET last_login = %s WHERE id = %s',
                      (now_utc, seller['id']))
        
        conn.commit()
        
        # Сохраняем в сессии Flask
        session['seller_logged_in'] = True
        session['seller_id'] = seller['id']
        session['seller_username'] = seller['username']
        session['display_name'] = seller.get('display_name') or seller['username']
        session['session_token'] = session_token
        session['login_time_local'] = utc_to_local(now_utc)
        
        # Логируем вход
        log_action(seller['id'], 'login', details=f'Вход с {flask_request.remote_addr}')
        
        print(f"✅ Успешный вход: {seller['username']}")
        return redirect(url_for('seller_dashboard'))
        
    except Exception as e:
        print(f"❌ Ошибка при входе: {e}")
        conn.rollback()
        return redirect(url_for('seller_login'))
    finally:
        cursor.close()

# ==================== МАРШРУТЫ ====================

@app.context_processor
def inject_now():
    """Добавляет текущую дату во все шаблоны"""
    return {'now': datetime.now()}

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/buyer')
def buyer():
    """Страница для покупателей"""
    items = execute_query('''
        SELECT id, name, sell_price, status, date_arrived 
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
    ''', fetchall=True)
    
    items_list = [dict(item) for item in items]
    in_stock = [item for item in items_list if item['status'] == 'в наличии']
    in_transit = [item for item in items_list if item['status'] == 'в пути']
    
    active_sellers = get_active_sellers()
    really_active_sellers = [s for s in active_sellers if s.get('is_really_active', False)]
    
    return render_template('buyer.html',
                         in_stock=in_stock,
                         in_transit=in_transit,
                         total=len(items_list),
                         active_sellers=really_active_sellers)

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    """Вход для продавца"""
    clear_old_sessions()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        seller = get_seller_by_username(username)
        
        if seller and bcrypt.check_password_hash(seller['password_hash'], password):
            # Проверяем активные сессии
            active_sessions = execute_query('''
                SELECT * FROM active_sessions 
                WHERE seller_id = %s AND is_active = TRUE
                ORDER BY last_activity DESC
                LIMIT 1
            ''', (seller['id'],), fetchall=True)
            
            if active_sessions and len(active_sessions) > 0:
                # Есть активная сессия - показываем предупреждение
                return render_template('login_warning.html',
                                     username=username,
                                     active_session=dict(active_sessions[0]))
            
            # Нет активной сессии - обычный вход
            return process_single_device_login(seller, request)
        else:
            return render_template('seller_login.html', error='Неверный логин или пароль')
    
    return render_template('seller_login.html')

@app.route('/seller/login_with_override', methods=['POST'])
def login_with_override():
    """Вход с завершением предыдущей сессии"""
    username = session.get('pending_username')
    if not username:
        return redirect(url_for('seller_login'))
    
    seller = get_seller_by_username(username)
    if not seller:
        return redirect(url_for('seller_login'))
    
    # Удаляем старую сессию
    execute_query('DELETE FROM active_sessions WHERE seller_id = %s', (seller['id'],))
    
    # Создаем новую
    return process_single_device_login(seller, request)

@app.route('/seller/dashboard')
def seller_dashboard():
    """Панель управления продавца"""
    if not session.get('seller_logged_in'):
        return redirect(url_for('seller_login'))
    
    # Проверяем сессию
    seller_id = session.get('seller_id')
    session_token = session.get('session_token')
    
    valid_session = execute_query('''
        SELECT 1 FROM active_sessions 
        WHERE seller_id = %s AND session_token = %s AND is_active = TRUE
    ''', (seller_id, session_token), fetchone=True)
    
    if not valid_session:
        session.clear()
        return redirect(url_for('seller_login'))
    
    # Обновляем активность
    execute_query('''
        UPDATE active_sessions 
        SET last_activity = %s
        WHERE session_token = %s AND seller_id = %s
    ''', (datetime.utcnow(), session_token, seller_id))
    
    # Получаем товары
    items = execute_query('SELECT * FROM items ORDER BY id DESC', fetchall=True)
    items_list = [dict(item) for item in items]
    
    # Статистика
    stats = {
        'total': len(items_list),
        'in_stock': len([i for i in items_list if i['status'] == 'в наличии']),
        'sold': len([i for i in items_list if i['status'] == 'продано']),
        'in_transit': len([i for i in items_list if i['status'] == 'в пути']),
    }
    
    recent_actions = get_recent_actions(limit=10)
    active_sellers_list = get_active_sellers()
    active_count = len([s for s in active_sellers_list if s.get('is_really_active', False)])
    
    return render_template('seller_dashboard.html',
                         items=items_list,
                         stats=stats,
                         recent_actions=recent_actions,
                         active_sellers=active_sellers_list,
                         active_count=active_count,
                         login_time_local=session.get('login_time_local', ''))

@app.route('/seller/add', methods=['POST'])
def add_item():
    """Добавить товар"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        
        # Вставляем товар
        execute_query('''
        INSERT INTO items (name, cost_price, sell_price, status, date_arrived)
        VALUES (%s, %s, %s, %s, %s)
        ''', (
            data['name'],
            float(data['cost_price']),
            float(data['sell_price']),
            data['status'],
            datetime.now().strftime('%Y-%m-%d')
        ))
        
        # Получаем ID вставленного товара
        item = execute_query('SELECT id FROM items ORDER BY id DESC LIMIT 1', fetchone=True)
        item_id = item['id']
        
        # Добавляем транзакцию если не "в пути"
        if data['status'] != 'в пути':
            execute_query('''
            INSERT INTO transactions (date, type, item_id, amount, note)
            VALUES (%s, %s, %s, %s, %s)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                'purchase',
                item_id,
                -float(data['cost_price']),
                f'Покупка {data["name"]}'
            ))
        
        log_action(session['seller_id'], 'add_item', item_id, f'Добавлен: {data["name"]}')
        return jsonify({'success': True, 'id': item_id})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', details=f'Ошибка добавления: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/update/<int:item_id>', methods=['POST'])
def update_item(item_id):
    """Обновить статус товара"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        new_status = data['status']
        
        # Получаем текущий статус
        item = execute_query('SELECT * FROM items WHERE id = %s', (item_id,), fetchone=True)
        if not item:
            return jsonify({'error': 'Товар не найден'}), 404
        
        old_status = item['status']
        
        # Обновляем статус
        if new_status == 'продано':
            execute_query('''
            UPDATE items SET status = %s, date_sold = %s WHERE id = %s
            ''', (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
            
            # Добавляем транзакцию продажи
            if old_status != 'продано':
                execute_query('''
                INSERT INTO transactions (date, type, item_id, amount, note)
                VALUES (%s, %s, %s, %s, %s)
                ''', (
                    datetime.now().strftime('%Y-%m-%d'),
                    'sale',
                    item_id,
                    float(item['sell_price']),
                    f'Продажа {item["name"]}'
                ))
        elif new_status == 'взял себе':
            execute_query('''
            UPDATE items SET status = %s, date_taken = %s WHERE id = %s
            ''', (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        else:
            execute_query('UPDATE items SET status = %s WHERE id = %s', (new_status, item_id))
        
        log_action(session['seller_id'], 'update_item', item_id, f'Статус: {old_status} → {new_status}')
        return jsonify({'success': True})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', details=f'Ошибка обновления: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца"""
    if session.get('seller_id'):
        seller_id = session['seller_id']
        execute_query('DELETE FROM active_sessions WHERE seller_id = %s', (seller_id,))
        log_action(seller_id, 'logout')
    
    session.clear()
    return redirect(url_for('index'))

@app.route('/seller/keepalive')
def keepalive():
    """Поддержание активности сессии"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    execute_query('''
    UPDATE active_sessions 
    SET last_activity = %s 
    WHERE session_token = %s AND seller_id = %s
    ''', (datetime.utcnow(), session['session_token'], session['seller_id']))
    
    return jsonify({'success': True})

@app.route('/buyer/active_sellers')
def buyer_active_sellers():
    """API для получения активных продавцов"""
    active_sellers = get_active_sellers()
    really_active = [s for s in active_sellers if s.get('is_really_active', False)]
    
    # Упрощаем данные для клиента
    simplified = []
    for seller in really_active:
        simplified.append({
            'id': seller['id'],
            'username': seller['username'],
            'display_name': seller.get('display_name') or seller['username'],
            'login_time_short': seller.get('login_time_short', '??:??')
        })
    
    return jsonify({'active_sellers': simplified})

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    # Инициализация БД при первом запуске
    with app.app_context():
        try:
            init_db()
        except Exception as e:
            print(f"⚠️ Ошибка инициализации БД: {e}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
