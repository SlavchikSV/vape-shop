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
    """Инициализация базы данных"""
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
        amount REAL,
        note TEXT
    )
    ''')
    
    # ТАБЛИЦА ПРОДАВЦОВ
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
    
    # ТАБЛИЦА ДЕЙСТВИЙ
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
    
    # ТАБЛИЦА АКТИВНЫХ СЕССИЙ
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
    
    # ТАБЛИЦА УВЕДОМЛЕНИЙ
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
    
    # Добавляем ТОЛЬКО SlavchikSV и mkozlov
    try:
        default_sellers = [
            ('SlavchikSV', 'sv280606', 'Администратор'),
            ('mkozlov', '020988mama', 'Главный администратор'),
        ]
        
        for username, password, display in default_sellers:
            # Проверяем, существует ли уже продавец
            existing = conn.execute('SELECT id FROM sellers WHERE username = ?', (username,)).fetchone()
            if not existing:
                password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
                conn.execute('''
                INSERT INTO sellers (username, password_hash, display_name, role)
                VALUES (?, ?, ?, ?)
                ''', (username, password_hash, display, 'admin' if username == 'SlavchikSV' else 'mkozlov'))
        
        print("✅ Созданы продавцы: SlavchikSV и mkozlov")
    except Exception as e:
        print(f"⚠️ Ошибка при создании продавцов: {e}")
    
    conn.commit()
    conn.close()

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
    """Конвертировать UTC время в локальное (UTC+3 для Минска)
    
    Args:
        utc_dt: datetime объект или строка
        format_only_time: если True, возвращает только время HH:MM
    """
    if not utc_dt:
        return ""
    
    try:
        if isinstance(utc_dt, str):
            # Пробуем разные форматы
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
                # Если не удалось распарсить, возвращаем как есть
                return utc_dt
            
            utc_dt = parsed_dt
        
        # Добавляем 3 часа для Минска (UTC+3)
        local_dt = utc_dt + timedelta(hours=3)
        
        if format_only_time:
            return local_dt.strftime('%H:%M')
        else:
            return local_dt.strftime('%H:%M:%S')
            
    except Exception as e:
        # Логируем ошибку для отладки
        print(f"Ошибка конвертации времени {utc_dt}: {e}")
        # Возвращаем оригинал или обрезаем
        if isinstance(utc_dt, str) and len(utc_dt) > 10:
            return utc_dt[11:16]  # HH:MM
        return str(utc_dt)

def log_action(seller_id, action_type, item_id=None, details="", ip_address=None):
    """Записать действие в лог"""
    try:
        conn = get_db()
        
        # Используем текущее UTC время
        created_at_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute('''
        INSERT INTO action_log (seller_id, action_type, item_id, details, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (seller_id, action_type, item_id, details, ip_address or request.remote_addr, created_at_utc))
        
        # 2. Получаем информацию о продавце
        seller = conn.execute('SELECT username, display_name FROM sellers WHERE id = ?', 
                             (seller_id,)).fetchone()
        
        seller_name = seller['display_name'] or seller['username']
        
        # 3. Если это ВЫХОД из системы - удаляем уведомления для этого продавца
        if action_type == 'logout':
            conn.execute('DELETE FROM notifications WHERE seller_id = ?', (seller_id,))
            print(f"🗑️ Удалены все уведомления для продавца {seller_name}")
        elif action_type != 'login':  # Для login не создаем уведомления
            # 4. Получаем ВСЕХ активных продавцов (кроме текущего)
            active_sellers = conn.execute('''
                SELECT DISTINCT seller_id FROM active_sessions 
                WHERE seller_id != ? AND is_active = 1
            ''', (seller_id,)).fetchall()
            
            # 5. Создаем понятное сообщение для уведомления
            action_messages = {
                'add_item': 'добавил новый товар',
                'update_item': 'изменил статус товара',
                'sale': 'продал товар',
                'purchase': 'купил товар для магазина',
                'personal': 'взял товар себе',
                'error': 'ошибка'
            }
            
            action_msg = action_messages.get(action_type, action_type)
            
            # Базовое сообщение
            message = f"{seller_name} {action_msg}"
            
            # Добавляем детали если есть
            if item_id and details:
                # Пытаемся получить название товара
                item = conn.execute('SELECT name FROM items WHERE id = ?', (item_id,)).fetchone()
                if item:
                    message += f": {item['name']}"
                else:
                    message += f": {details[:50]}"
            elif details:
                message += f": {details[:50]}"
            
            # 6. Создаем уведомления только для АКТИВНЫХ продавцов
            for active_seller in active_sellers:
                # Проверяем, активен ли еще получатель уведомления
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
        print(f"📝 Действие записано: {seller_id} - {action_type} в {created_at_utc} UTC")
        
    except Exception as e:
        print(f"❌ Ошибка при записи лога: {e}")
    finally:
        conn.close()

def get_recent_actions(limit=10):
    """Получить последние действия с правильным временем"""
    conn = get_db()
    
    # Получаем действия из базы
    actions = conn.execute('''
        SELECT al.*, s.username, s.display_name
        FROM action_log al
        LEFT JOIN sellers s ON al.seller_id = s.id
        ORDER BY al.created_at DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    
    conn.close()
    
    # Конвертируем в список словарей и корректируем время
    actions_list = []
    for action in actions:
        action_dict = dict(action)
        
        # Конвертируем время created_at из UTC в локальное
        if action_dict['created_at']:
            try:
                # Пробуем разные форматы времени
                utc_time = None
                created_str = str(action_dict['created_at'])
                
                # Если это строка с датой и временем
                if ' ' in created_str:
                    try:
                        utc_time = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        try:
                            utc_time = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S.%f')
                        except:
                            utc_time = None
                
                # Конвертируем в локальное время
                if utc_time:
                    local_time = utc_time + timedelta(hours=3)
                    # Форматируем для отображения: "ДД.ММ.ГГГГ ЧЧ:ММ:СС"
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
        # Удаляем сессии старше 8 часов
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
    
    # Конвертируем время и определяем статус
    result = []
    now = datetime.utcnow()
    
    for seller in sellers:
        seller_dict = dict(seller)
        
        # Конвертируем время входа в локальное
        login_time_utc = datetime.strptime(seller_dict['login_time'], '%Y-%m-%d %H:%M:%S')
        seller_dict['login_time_local'] = utc_to_local(login_time_utc)
        seller_dict['login_time_short'] = seller_dict['login_time_local'][:5]  # HH:MM
        
        # Определяем активность (5 минут бездействия = неактивен)
        last_activity_utc = datetime.strptime(seller_dict['last_activity'], '%Y-%m-%d %H:%M:%S')
        minutes_since_activity = (now - last_activity_utc).total_seconds() / 60
        
        # Действительно активен, если был активен в последние 5 минут
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
    """Создание новой сессии с удалением старых (один пользователь = одно устройство)"""
    # СНАЧАЛА удаляем старые сессии
    conn = get_db()
    
    try:
        # УДАЛЯЕМ ВСЕ предыдущие сессии этого пользователя
        deleted_count = conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', 
                                    (seller['id'],)).rowcount
        
        if deleted_count > 0:
            print(f"🗑️ Удалено {deleted_count} старых сессий для {seller['username']}")
            log_action(seller['id'], 'auto_logout_old', 
                      details=f'Удалено {deleted_count} старых сессий при новом входе')
        
        # ПОТОМ создаем новую сессию
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
        
        # Сохраняем в сессии Flask
        session['seller_logged_in'] = True
        session['seller_id'] = seller['id']
        session['seller_username'] = seller['username']
        session['display_name'] = seller.get('display_name') or seller['username']
        session['session_token'] = session_token
        
        # Сохраняем время входа
        login_time_utc = datetime.utcnow()
        session['login_time_utc'] = login_time_utc.strftime('%Y-%m-%d %H:%M:%S')
        session['login_time_local'] = utc_to_local(login_time_utc)
        
        # Обновляем время последнего входа в профиле
        conn.execute('UPDATE sellers SET last_login = ? WHERE id = ?',
                    (login_time_utc.strftime('%Y-%m-%d %H:%M:%S'), seller['id']))
        conn.commit()
        
        # Логируем успешный вход
        log_action(seller['id'], 'login', 
                  details=f'Вход с {flask_request.remote_addr}')
        
        print(f"✅ Успешный вход: {seller['username']} с IP {flask_request.remote_addr}")
        print(f"   Новый токен сессии: {session_token[:20]}...")
        
        return redirect(url_for('seller_dashboard'))
        
    except Exception as e:
        print(f"❌ Ошибка при входе для {seller['username']}: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('seller_login'))
        
    finally:
        conn.close()

def clear_old_pending_logins():
    """Очистка устаревших pending логинов из сессии"""
    pending_login = session.get('pending_login')
    if pending_login:
        if datetime.now().timestamp() - pending_login['timestamp'] > 600:  # 10 минут
            session.pop('pending_login', None)
            print("🧹 Очищен устаревший pending логин")

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
    conn = get_db()
    
    # ИСПРАВЛЯЕМ ЗДЕСЬ: Загружаем все товары "в наличии" и "в пути"
    items = conn.execute('''
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
    ''').fetchall()
    
    conn.close()
    
    # Преобразуем в список словарей
    items_list = [dict(item) for item in items]
    
    # Группируем для шаблона
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

@app.before_request
def check_session_middleware():
    """Проверяем валидность сессии для маршрутов продавца"""
    # Проверяем только маршруты /seller/ кроме исключений
    if request.path.startswith('/seller/'):
        excluded_paths = [
            '/seller/login',
            '/seller/logout', 
            '/seller/session_expired',
            '/seller/check_session',
            '/seller/active_sellers_count_public',
            '/seller/active_sellers_list_public',
            '/seller/login_with_override'  # ← ДОБАВЬТЕ ЭТО!
        ]
        
        # Если это исключенный путь - пропускаем
        if any(request.path == path or request.path.startswith(path + '/') for path in excluded_paths):
            return
        
        # Проверяем авторизацию
        if not session.get('seller_logged_in') or not session.get('session_token'):
            return redirect(url_for('session_expired'))
        
        # Проверяем валидность сессии в базе
        seller_id = session['seller_id']
        session_token = session['session_token']
        
        conn = get_db()
        current_session = conn.execute('''
            SELECT 1 FROM active_sessions 
            WHERE seller_id = ? AND session_token = ? AND is_active = 1
        ''', (seller_id, session_token)).fetchone()
        conn.close()
        
        if not current_session:
            # Сессия не найдена - нас вытеснили
            print(f"🚨 Сессия не найдена! seller_id={seller_id}, token={session_token[:20]}...")
            session.clear()
            return redirect(url_for('session_expired'))

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    """Вход для продавца"""
    clear_old_sessions()
    clear_old_pending_logins()
    
    # Проверяем параметр expired (если нас вытеснили)
    expired = request.args.get('expired')
    expired_message = None
    if expired:
        expired_message = 'Вы были автоматически выведены из системы с другого устройства.'
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Ищем продавца в базе
        seller = get_seller_by_username(username)
        
        if seller and bcrypt.check_password_hash(seller['password_hash'], password):
            # Проверяем, есть ли активные сессии
            conn = get_db()
            active_sessions = conn.execute('''
                SELECT * FROM active_sessions 
                WHERE seller_id = ? AND is_active = 1
                ORDER BY last_activity DESC
                LIMIT 1
            ''', (seller['id'],)).fetchall()
            conn.close()
            
            if active_sessions and len(active_sessions) > 0:
                # СОХРАНЯЕМ ДАННЫЕ В СЕССИИ, а не передаем в шаблон
                session['pending_login'] = {
                    'username': username,
                    'seller_id': seller['id'],
                    'timestamp': datetime.now().timestamp()
                }
                
                # Есть активная сессия - показываем предупреждение
                return render_template('login_warning.html',
                                     username=username,
                                     active_session=dict(active_sessions[0]),
                                     expired_message=expired_message)
            
            # Если нет активной сессии - обычный вход
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
    # Проверяем временную сессию
    pending_login = session.get('pending_login')
    
    if not pending_login:
        return redirect(url_for('seller_login'))
    
    # Проверяем, не устарели ли данные (10 минут)
    if datetime.now().timestamp() - pending_login['timestamp'] > 600:
        session.pop('pending_login', None)
        return redirect(url_for('seller_login'))
    
    # Получаем продавца
    seller = get_seller_by_username(pending_login['username'])
    
    if not seller:
        session.pop('pending_login', None)
        return redirect(url_for('seller_login'))
    
    # Логируем принудительное завершение предыдущей сессии
    conn = get_db()
    old_session = conn.execute('''
        SELECT * FROM active_sessions 
        WHERE seller_id = ? AND is_active = 1
    ''', (seller['id'],)).fetchone()
    
    if old_session:
        log_action(seller['id'], 'force_logout', 
                  details=f'Принудительно завершена сессия с IP {old_session["ip_address"]}')
        print(f"🔒 Принудительно завершаем сессию для {pending_login['username']}")
    
    # Удаляем старую сессию
    conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', (seller['id'],))
    conn.commit()
    conn.close()
    
    # Очищаем временную сессию
    session.pop('pending_login', None)
    
    # Создаем новую сессию
    return process_single_device_login(seller, request)  

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца - удаляем ВСЕ сессии пользователя"""
    if session.get('seller_id'):
        seller_id = session['seller_id']
        username = session.get('seller_username', 'Unknown')
        
        # Удаляем все сессии этого пользователя
        conn = get_db()
        conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', (seller_id,))
        conn.commit()
        conn.close()
        
        # Логируем выход
        log_action(seller_id, 'logout', details=f'Выход из системы ({username})')
    
    # Очищаем сессию Flask
    session.clear()
    return redirect(url_for('index'))

@app.route('/seller/session_expired')
def session_expired():
    """Страница уведомления о завершенной сессии"""
    return render_template('session_expired.html')

@app.route('/seller/dashboard')
def seller_dashboard():
    """Панель управления продавца"""
    # Проверяем, не вытеснены ли мы
    if not session.get('seller_logged_in') or not session.get('session_token'):
        return redirect(url_for('session_expired'))
    
    seller_id = session.get('seller_id')
    session_token = session.get('session_token')
    
    # 2. Подключаемся к базе
    conn = get_db()
    
    try:
        # 3. Проверяем и исправляем множественные сессии
        # Получаем ВСЕ активные сессии этого пользователя
        active_sessions = conn.execute('''
            SELECT session_token, ip_address, user_agent, login_time, last_activity
            FROM active_sessions 
            WHERE seller_id = ? AND is_active = 1
            ORDER BY last_activity DESC
        ''', (seller_id,)).fetchall()
        
        # Конвертируем в список словарей для логирования
        sessions_list = [dict(sess) for sess in active_sessions]
        
        # Если больше одной сессии - это нарушение политики
        if len(sessions_list) > 1:
            print(f"⚠️  Нарушение политики! У пользователя ID {seller_id} найдено {len(sessions_list)} активных сессий:")
            for sess in sessions_list:
                print(f"   - Токен: {sess['session_token'][:20]}..., IP: {sess['ip_address']}, Устройство: {sess['user_agent'][:50]}")
            
            # Находим текущую сессию (должна быть в списке)
            current_session_exists = any(sess['session_token'] == session_token for sess in sessions_list)
            
            if current_session_exists:
                # Удаляем ВСЕ сессии, кроме текущей
                conn.execute('''
                DELETE FROM active_sessions 
                WHERE seller_id = ? AND session_token != ?
                ''', (seller_id, session_token))
                conn.commit()
                print(f"✅ Оставлена только текущая сессия, остальные удалены")
                
                # Логируем это событие
                log_action(seller_id, 'session_cleanup', 
                          details=f'Удалено {len(sessions_list)-1} лишних сессий')
            else:
                # Текущая сессия не найдена в активных - что-то не так
                print(f"🚨 Текущая сессия не найдена в активных! Очищаем все и просим перелогиниться")
                conn.execute('DELETE FROM active_sessions WHERE seller_id = ?', (seller_id,))
                conn.commit()
                session.clear()
                conn.close()
                return redirect(url_for('seller_login'))
        
        # 4. Проверяем, что текущая сессия валидна
        current_session = conn.execute('''
            SELECT s.username, s.display_name, a.login_time, a.last_activity
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.session_token = ? AND a.seller_id = ? AND a.is_active = 1
        ''', (session_token, seller_id)).fetchone()
        
        if not current_session:
            print(f"🚨 Сессия не найдена в базе: seller_id={seller_id}, token={session_token[:20]}...")
            session.clear()
            conn.close()
            return redirect(url_for('seller_login'))
        
        # 5. Обновляем время последней активности
        conn.execute('''
        UPDATE active_sessions 
        SET last_activity = ?
        WHERE session_token = ? AND seller_id = ?
        ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), session_token, seller_id))
        conn.commit()
        
        # 6. Получаем товары для панели управления
        items = conn.execute('''
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
        ''').fetchall()
        
        conn.close()
        
        # 7. Подготавливаем данные для шаблона
        items_list = [dict(item) for item in items]
        
        # Статистика
        stats = {
            'total': len(items_list),
            'in_stock': len([i for i in items_list if i['status'] == 'в наличии']),
            'sold': len([i for i in items_list if i['status'] == 'продано']),
            'in_transit': len([i for i in items_list if i['status'] == 'в пути']),
            'personal': len([i for i in items_list if i['status'] == 'взял себе']),
        }
        
        # Последние действия
        recent_actions = get_recent_actions(limit=10)
        
        # Активные продавцы
        active_sellers_list = get_active_sellers()
        
        # Количество действительно активных продавцов
        active_count = len([s for s in active_sellers_list if s.get('is_really_active', False)])
        
        # 8. Логируем успешный доступ
        print(f"✅ Успешный доступ к панели: {current_session['username']} (сессия: {session_token[:20]}...)")
        
        # 9. Рендерим шаблон
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
    """Добавить товар (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO items (name, cost_price, sell_price, status, date_arrived)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            data['name'],
            float(data['cost_price']),
            float(data['sell_price']),
            data['status'],
            datetime.now().strftime('%Y-%m-%d')
        ))
        
        item_id = cursor.lastrowid
        
        # Добавляем транзакцию покупки (если не "в пути")
        if data['status'] != 'в пути':
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
        
        conn.commit()
        conn.close()
        
        # Логируем действие
        log_action(session['seller_id'], 'add_item', item_id, 
                  f'Добавлен товар: {data["name"]}')
        
        return jsonify({'success': True, 'id': item_id})
        
    except Exception as e:
        log_action(session.get('seller_id'), 'error', details=f'Ошибка добавления: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/seller/update/<int:item_id>', methods=['POST'])
def update_item(item_id):
    """Обновить статус товара (AJAX)"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        new_status = data['status']
        
        conn = get_db()
        
        # Получаем текущие данные
        item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            conn.close()
            return jsonify({'error': 'Товар не найден'}), 404
        
        old_status = item['status']
        
        # Обновляем статус
        date_field = ''
        if new_status == 'продано':
            date_field = ', date_sold = ?'
        elif new_status == 'взял себе':
            date_field = ', date_taken = ?'
        
        query = f'UPDATE items SET status = ?{date_field} WHERE id = ?'
        
        if date_field:
            conn.execute(query, (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        else:
            conn.execute(query, (new_status, item_id))
        
        # Добавляем транзакцию продажи
        if old_status != 'продано' and new_status == 'продано':
            conn.execute('''
            INSERT INTO transactions (date, type, item_id, amount, note)
            VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                'sale',
                item_id,
                float(item['sell_price']),
                f'Продажа {item["name"]}'
            ))
        
        conn.commit()
        conn.close()
        
        # Логируем действие
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
    
    # Обновляем время активности
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
    
    # Преобразуем в список словарей
    notifications_list = [dict(n) for n in notifications]
    
    # Помечаем как прочитанные
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
    """Количество активных продавцов (публичный доступ, без авторизации)"""
    # Очищаем старые сессии
    clear_old_sessions()
    
    conn = get_db()
    
    # Считаем только действительно активных продавцов (последние 5 минут)
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
    # Очищаем старые сессии
    clear_old_sessions()
    
    conn = get_db()
    
    # Берем только действительно активных (последние 5 минут)
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
    
    # Форматируем данные
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
        # Также очищаем сессию Flask
        print(f"🔍 AJAX проверка: сессия не найдена для {seller_id}")
        session.clear()
        return jsonify({'valid': False, 'reason': 'session_replaced'}), 401

@app.route('/buyer/active_sellers')
def buyer_active_sellers():
    """API для получения активных продавцов (AJAX) - оптимизированная версия"""
    conn = get_db()
    
    # Берем только действительно активных продавцов (последние 10 минут)
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
    
    # Упрощаем и форматируем данные
    simplified_sellers = []
    for seller in sellers:
        try:
            login_time = seller['login_time']
            if isinstance(login_time, str):
                # Конвертируем UTC в локальное время
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
    
    # ВАЖНО: Всегда возвращаем JSON, даже если пустой массив
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
    # Инициализируем базу данных
    init_db()
    
    # Очищаем старые сессии при запуске
    clear_old_sessions()
    
    # Запускаем сервер
    port = int(os.environ.get('PORT', 5000))

    app.run(host='0.0.0.0', port=port, debug=False)
