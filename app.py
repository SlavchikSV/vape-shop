import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
from flask_bcrypt import Bcrypt
import psycopg2
from psycopg2.extras import DictCursor, RealDictCursor
from datetime import datetime, timedelta
import secrets
import pytz
from decimal import Decimal

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
bcrypt = Bcrypt(app)

# Московское время (UTC+3)
msk_tz = pytz.timezone('Europe/Moscow')

# ==================== БАЗА ДАННЫХ ====================
def get_db():
    """Подключение к PostgreSQL"""
    if 'db' not in g:
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            raise Exception("DATABASE_URL не установлен!")
        
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        conn.cursor_factory = RealDictCursor
        g.db = conn
    
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Закрыть соединение с БД"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def utc_to_msk(utc_dt):
    """Конвертировать UTC в московское время"""
    if not utc_dt:
        return ""
    
    if isinstance(utc_dt, str):
        try:
            utc_dt = datetime.strptime(utc_dt, '%Y-%m-%d %H:%M:%S')
        except:
            return utc_dt
    
    utc_dt = pytz.utc.localize(utc_dt)
    msk_dt = utc_dt.astimezone(msk_tz)
    return msk_dt

def format_msk_time(dt, format_str='%H:%M'):
    """Форматировать московское время"""
    if not dt:
        return ""
    return dt.strftime(format_str)

def init_db():
    """Инициализация базы данных"""
    print("🔄 Создание таблиц в PostgreSQL...")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Таблица поставок
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS shipments (
            id SERIAL PRIMARY KEY,
            shipment_number VARCHAR(50) UNIQUE NOT NULL,
            order_date DATE NOT NULL,
            received_date DATE,
            delivery_cost DECIMAL(10,2) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'в пути',
            total_items INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица товаров
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            cost_price DECIMAL(10,2) NOT NULL,
            sell_price DECIMAL(10,2) NOT NULL,
            manual_price DECIMAL(10,2),
            status VARCHAR(20) NOT NULL,
            shipment_id INTEGER REFERENCES shipments(id) ON DELETE SET NULL,
            date_arrived DATE,
            date_sold DATE,
            date_taken DATE,
            date_reserved DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица транзакций
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            type VARCHAR(20) NOT NULL,
            shipment_id INTEGER REFERENCES shipments(id) ON DELETE SET NULL,
            item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
            amount DECIMAL(10,2) NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица продавцов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sellers (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            display_name VARCHAR(100),
            role VARCHAR(20) DEFAULT 'seller',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        ''')
        
        # Таблица активных сессий
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_sessions (
            id SERIAL PRIMARY KEY,
            seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
            session_token VARCHAR(255) UNIQUE NOT NULL,
            ip_address VARCHAR(50),
            user_agent TEXT,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
        ''')
        
        # Добавляем стандартных продавцов
        default_sellers = [
            ('SlavchikSV', 'sv280606', 'Администратор', 'admin'),
            ('mkozlov', '020988mama', 'Главный администратор', 'admin'),
            ('g_nix', 'IHHujhg655G', 'Григорий', 'seller'),
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
        print("✅ База данных инициализирована")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Выполнить SQL запрос"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute(query, params)
        
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        else:
            result = cursor.rowcount
        
        if commit:
            conn.commit()
        
        return result
    except Exception as e:
        conn.rollback()
        print(f"❌ SQL ошибка: {e}")
        print(f"   Запрос: {query}")
        print(f"   Параметры: {params}")
        raise
    finally:
        cursor.close()

def get_current_capital():
    """Получить текущий капитал (сумма всех транзакций)"""
    try:
        result = execute_query(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions",
            fetchone=True
        )
        return float(result['total']) if result else 0
    except:
        return 0

def get_active_sellers():
    """Получить список активных продавцов (последние 5 минут)"""
    try:
        five_minutes_ago = (datetime.utcnow() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        
        sellers = execute_query('''
            SELECT s.id, s.username, s.display_name, a.login_time
            FROM active_sessions a
            JOIN sellers s ON a.seller_id = s.id
            WHERE a.is_active = TRUE AND a.last_activity > %s
            ORDER BY a.last_activity DESC
        ''', (five_minutes_ago,), fetchall=True)
        
        result = []
        for seller in sellers:
            login_time = utc_to_msk(seller['login_time'])
            result.append({
                'id': seller['id'],
                'username': seller['username'],
                'display_name': seller['display_name'] or seller['username'],
                'login_time_short': format_msk_time(login_time, '%H:%M'),
                'login_time_full': format_msk_time(login_time, '%d.%m.%Y %H:%M')
            })
        
        return result
    except:
        return []

def update_shipment_status(shipment_id, new_status, delivery_cost=None):
    """Обновить статус поставки"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        shipment = execute_query(
            'SELECT * FROM shipments WHERE id = %s',
            (shipment_id,), fetchone=True
        )
        
        if not shipment:
            return False
        
        old_status = shipment['status']
        
        if new_status == 'в наличии' and old_status == 'в пути':
            # Обновляем статус поставки
            cursor.execute('''
            UPDATE shipments 
            SET status = %s, received_date = CURRENT_DATE,
                delivery_cost = COALESCE(%s, delivery_cost),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            ''', (new_status, delivery_cost, shipment_id))
            
            # Обновляем статус товаров
            cursor.execute('''
            UPDATE items 
            SET status = 'в наличии', date_arrived = CURRENT_DATE
            WHERE shipment_id = %s AND status = 'в пути'
            ''', (shipment_id,))
            
            # Добавляем транзакцию доставки
            if delivery_cost and float(delivery_cost) > 0:
                cursor.execute('''
                INSERT INTO transactions (date, type, shipment_id, amount, note)
                VALUES (CURRENT_DATE, 'доставка', %s, %s, %s)
                ''', (shipment_id, -float(delivery_cost), f'Доставка поставки {shipment["shipment_number"]}'))
            
            # Добавляем транзакции закупки товаров
            items = execute_query(
                'SELECT id, name, cost_price FROM items WHERE shipment_id = %s',
                (shipment_id,), fetchall=True
            )
            
            for item in items:
                cursor.execute('''
                INSERT INTO transactions (date, type, item_id, amount, note)
                VALUES (CURRENT_DATE, 'закупка', %s, %s, %s)
                ''', (item['id'], -float(item['cost_price']), f'Закупка: {item["name"]}'))
        
        elif new_status == 'продано':
            # Проверяем, все ли товары проданы
            cursor.execute('''
            SELECT COUNT(*) as total_items,
                   SUM(CASE WHEN status = 'продано' THEN 1 ELSE 0 END) as sold_items
            FROM items WHERE shipment_id = %s
            ''', (shipment_id,))
            
            stats = cursor.fetchone()
            
            if stats['total_items'] == stats['sold_items']:
                cursor.execute('''
                UPDATE shipments SET status = 'продано', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                ''', (shipment_id,))
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка обновления статуса поставки: {e}")
        return False
    finally:
        cursor.close()

# ==================== МАРШРУТЫ ====================

@app.route('/')
def index():
    """Перенаправление на страницу покупателя"""
    return redirect(url_for('buyer'))

@app.route('/buyer')
def buyer():
    """Страница для покупателей"""
    try:
        # Только товары "в наличии" (без зарезервированных)
        items = execute_query('''
            SELECT id, name, sell_price, manual_price, 
                   COALESCE(manual_price, sell_price) as display_price
            FROM items 
            WHERE status = 'в наличии'
            ORDER BY created_at DESC
        ''', fetchall=True)
        
        active_sellers = get_active_sellers()
        capital = get_current_capital()
        
        return render_template('buyer.html',
                             items=items,
                             active_sellers=active_sellers,
                             active_count=len(active_sellers),
                             capital=capital)
    except Exception as e:
        print(f"❌ Ошибка в /buyer: {e}")
        return render_template('buyer.html',
                             items=[],
                             active_sellers=[],
                             active_count=0,
                             capital=0)

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    """Вход для продавца"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        seller = execute_query(
            'SELECT * FROM sellers WHERE username = %s',
            (username,), fetchone=True
        )
        
        if seller and bcrypt.check_password_hash(seller['password_hash'], password):
            # Удаляем старые сессии
            execute_query(
                'DELETE FROM active_sessions WHERE seller_id = %s',
                (seller['id'],), commit=True
            )
            
            # Создаем новую сессию
            session_token = secrets.token_hex(32)
            execute_query('''
            INSERT INTO active_sessions 
            (seller_id, session_token, ip_address, user_agent)
            VALUES (%s, %s, %s, %s)
            ''', (
                seller['id'], session_token,
                request.remote_addr, request.user_agent.string[:200]
            ), commit=True)
            
            # Обновляем last_login
            execute_query(
                'UPDATE sellers SET last_login = CURRENT_TIMESTAMP WHERE id = %s',
                (seller['id'],), commit=True
            )
            
            # Сохраняем в сессии
            session['seller_id'] = seller['id']
            session['seller_username'] = seller['username']
            session['display_name'] = seller['display_name'] or seller['username']
            session['session_token'] = session_token
            session['login_time'] = datetime.utcnow().isoformat()
            
            return redirect(url_for('seller_dashboard'))
        else:
            return render_template('seller_login.html', error='Неверный логин или пароль')
    
    return render_template('seller_login.html')

@app.route('/seller/dashboard')
def seller_dashboard():
    """Панель продавца"""
    if not session.get('seller_id'):
        return redirect(url_for('seller_login'))
    
    # Проверяем сессию
    valid_session = execute_query('''
        SELECT 1 FROM active_sessions 
        WHERE seller_id = %s AND session_token = %s AND is_active = TRUE
    ''', (session['seller_id'], session['session_token']), fetchone=True)
    
    if not valid_session:
        session.clear()
        return redirect(url_for('seller_login'))
    
    # Обновляем активность
    execute_query('''
        UPDATE active_sessions SET last_activity = CURRENT_TIMESTAMP
        WHERE seller_id = %s AND session_token = %s
    ''', (session['seller_id'], session['session_token']), commit=True)
    
    # Получаем данные
    items = execute_query('''
        SELECT i.*, s.shipment_number
        FROM items i
        LEFT JOIN shipments s ON i.shipment_id = s.id
        ORDER BY i.created_at DESC
    ''', fetchall=True)
    
    shipments = execute_query('''
        SELECT s.*, 
               COUNT(i.id) as item_count,
               SUM(i.cost_price) as total_cost
        FROM shipments s
        LEFT JOIN items i ON s.id = i.shipment_id
        GROUP BY s.id
        ORDER BY s.order_date DESC
    ''', fetchall=True)
    
    active_sellers = get_active_sellers()
    capital = get_current_capital()
    
    # Статистика
    stats = {
        'total': len(items),
        'in_stock': len([i for i in items if i['status'] == 'в наличии']),
        'in_transit': len([i for i in items if i['status'] == 'в пути']),
        'reserved': len([i for i in items if i['status'] == 'зарезервировано']),
        'sold': len([i for i in items if i['status'] == 'продано']),
        'personal': len([i for i in items if i['status'] == 'взял себе']),
    }
    
    return render_template('seller_dashboard.html',
                         items=items,
                         shipments=shipments,
                         stats=stats,
                         active_sellers=active_sellers,
                         active_count=len(active_sellers),
                         capital=capital)

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца"""
    if session.get('seller_id'):
        execute_query(
            'DELETE FROM active_sessions WHERE seller_id = %s',
            (session['seller_id'],), commit=True
        )
    
    session.clear()
    return redirect(url_for('index'))

@app.route('/seller/shipments/create', methods=['POST'])
def create_shipment():
    """Создать поставку"""
    if not session.get('seller_id'):
        return jsonify({'error': 'Не авторизован'}), 401
    
    try:
        data = request.get_json()
        
        # Генерируем номер поставки
        last_shipment = execute_query(
            "SELECT shipment_number FROM shipments ORDER BY id DESC LIMIT 1",
            fetchone=True
        )
        
        if last_shipment and 'SHIP-' in last_shipment['shipment_number']:
            last_num = int(last_shipment['shipment_number'].split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        shipment_number = f"SHIP-{new_num:03d}"
        
        # Создаем поставку
        shipment_id = execute_query('''
            INSERT INTO shipments (shipment_number, order_date, delivery_cost)
            VALUES (%s, %s, %s) RETURNING id
        ''', (shipment_number, data['order_date'], data.get('delivery_cost', 0)), 
        fetchone=True)['id']
        
        # Добавляем товары если есть
        if 'items' in data and data['items']:
            for item in data['items']:
                execute_query('''
                    INSERT INTO items 
                    (name, cost_price, sell_price, status, shipment_id)
                    VALUES (%s, %s, %s, 'в пути', %s)
                ''', (
                    item['name'],
                    item['cost_price'],
                    item['sell_price'],
                    shipment_id
                ), commit=True)
            
            # Обновляем счетчик товаров
            execute_query('''
                UPDATE shipments SET total_items = %s 
                WHERE id = %s
            ''', (len(data['items']), shipment_id), commit=True)
        
        return jsonify({
            'success': True,
            'shipment_id': shipment_id,
            'shipment_number': shipment_number
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/shipments/<int:shipment_id>/update_status', methods=['POST'])
def update_shipment_status_route(shipment_id):
    """Обновить статус поставки"""
    if not session.get('seller_id'):
        return jsonify({'error': 'Не авторизован'}), 401
    
    try:
        data = request.get_json()
        new_status = data['status']
        delivery_cost = data.get('delivery_cost')
        
        if update_shipment_status(shipment_id, new_status, delivery_cost):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Не удалось обновить статус'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/items/add', methods=['POST'])
def add_item():
    """Добавить товар"""
    if not session.get('seller_id'):
        return jsonify({'error': 'Не авторизован'}), 401
    
    try:
        data = request.get_json()
        
        item_id = execute_query('''
            INSERT INTO items (name, cost_price, sell_price, status, shipment_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (
            data['name'],
            data['cost_price'],
            data['sell_price'],
            data['status'],
            data.get('shipment_id')
        ), fetchone=True)['id']
        
        # Если товар привязан к поставке, обновляем счетчик
        if data.get('shipment_id'):
            execute_query('''
                UPDATE shipments SET total_items = total_items + 1
                WHERE id = %s
            ''', (data['shipment_id'],), commit=True)
        
        # Если товар сразу "в наличии", добавляем транзакцию
        if data['status'] == 'в наличии':
            execute_query('''
                INSERT INTO transactions (date, type, item_id, amount, note)
                VALUES (CURRENT_DATE, 'закупка', %s, %s, %s)
            ''', (item_id, -float(data['cost_price']), f'Закупка: {data["name"]}'), commit=True)
        
        return jsonify({'success': True, 'id': item_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/items/<int:item_id>/update_status', methods=['POST'])
def update_item_status(item_id):
    """Обновить статус товара"""
    if not session.get('seller_id'):
        return jsonify({'error': 'Не авторизован'}), 401
    
    try:
        data = request.get_json()
        new_status = data['status']
        
        # Получаем текущий статус
        item = execute_query(
            'SELECT * FROM items WHERE id = %s',
            (item_id,), fetchone=True
        )
        
        if not item:
            return jsonify({'error': 'Товар не найден'}), 404
        
        old_status = item['status']
        
        # Обновляем статус
        if new_status == 'продано':
            execute_query('''
                UPDATE items SET status = %s, date_sold = CURRENT_DATE
                WHERE id = %s
            ''', (new_status, item_id), commit=True)
            
            # Добавляем транзакцию продажи
            sell_price = float(item['manual_price'] or item['sell_price'])
            execute_query('''
                INSERT INTO transactions (date, type, item_id, amount, note)
                VALUES (CURRENT_DATE, 'продажа', %s, %s, %s)
            ''', (item_id, sell_price, f'Продажа: {item["name"]}'), commit=True)
            
            # Проверяем, все ли товары в поставке проданы
            if item['shipment_id']:
                update_shipment_status(item['shipment_id'], 'продано')
                
        elif new_status == 'в наличии':
            execute_query('''
                UPDATE items SET status = %s, date_arrived = CURRENT_DATE
                WHERE id = %s
            ''', (new_status, item_id), commit=True)
            
            # Если меняем с "в пути" на "в наличии", добавляем транзакцию
            if old_status == 'в пути':
                execute_query('''
                    INSERT INTO transactions (date, type, item_id, amount, note)
                    VALUES (CURRENT_DATE, 'закупка', %s, %s, %s)
                ''', (item_id, -float(item['cost_price']), f'Закупка: {item["name"]}'), commit=True)
        
        else:
            execute_query('''
                UPDATE items SET status = %s WHERE id = %s
            ''', (new_status, item_id), commit=True)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/items/<int:item_id>/update_price', methods=['POST'])
def update_item_price(item_id):
    """Обновить цену товара"""
    if not session.get('seller_id'):
        return jsonify({'error': 'Не авторизован'}), 401
    
    try:
        data = request.get_json()
        new_price = float(data['price'])
        
        execute_query('''
            UPDATE items SET manual_price = %s WHERE id = %s
        ''', (new_price, item_id), commit=True)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/transactions')
def get_transactions():
    """Получить список транзакций"""
    if not session.get('seller_id'):
        return jsonify({'error': 'Не авторизован'}), 401
    
    transactions = execute_query('''
        SELECT t.*, s.shipment_number, i.name as item_name
        FROM transactions t
        LEFT JOIN shipments s ON t.shipment_id = s.id
        LEFT JOIN items i ON t.item_id = i.id
        ORDER BY t.date DESC, t.created_at DESC
        LIMIT 100
    ''', fetchall=True)
    
    capital = get_current_capital()
    
    return jsonify({
        'transactions': transactions,
        'capital': capital
    })

@app.route('/seller/active_sellers_list')
def get_active_sellers_list():
    """Получить список активных продавцов (AJAX)"""
    sellers = get_active_sellers()
    return jsonify({'active_sellers': sellers})

@app.route('/seller/keepalive')
def keepalive():
    """Поддержание активности сессии"""
    if session.get('seller_id') and session.get('session_token'):
        execute_query('''
            UPDATE active_sessions SET last_activity = CURRENT_TIMESTAMP
            WHERE seller_id = %s AND session_token = %s
        ''', (session['seller_id'], session['session_token']), commit=True)
    
    return jsonify({'success': True})

# ==================== API ДЛЯ ПОКУПАТЕЛЯ ====================

@app.route('/api/active_sellers')
def api_active_sellers():
    """API для получения активных продавцов"""
    sellers = get_active_sellers()
    return jsonify({'active_sellers': sellers})

# ==================== ЗАПУСК ====================

# Инициализация БД при запуске
with app.app_context():
    try:
        init_db()
        print("✅ База данных готова")
    except Exception as e:
        print(f"⚠️ Ошибка при инициализации БД: {e}")

# Render требует явного указания порта в gunicorn
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Запуск сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

