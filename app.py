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
        traceback.print_exc()
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
        print(f"❌ Ошибка SQL запроса: {e}")
        print(f"   Запрос: {query}")
        print(f"   Параметры: {params}")
        
        # Если таблицы не существуют, создаем их
        if "does not exist" in str(e) or "relation" in str(e):
            print("🔄 Попытка создать таблицы...")
            try:
                init_db()
                # Повторяем запрос после создания таблиц
                cursor.execute(query, params)
                if fetchone:
                    result = cursor.fetchone()
                elif fetchall:
                    result = cursor.fetchall()
                else:
                    conn.commit()
                    result = cursor.rowcount
                return result
            except Exception as e2:
                print(f"❌ Не удалось создать таблицы: {e2}")
        
        raise e
    finally:
        cursor.close()

# ... (остальные функции остаются как были) ...

# ==================== МАРШРУТЫ ====================

@app.before_request
def before_first_request():
    """Создать таблицы при первом запросе, если их нет"""
    try:
        # Проверяем, есть ли таблица items
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM items LIMIT 1")
        cursor.close()
    except:
        # Таблицы нет - создаем
        print("📦 Таблицы не найдены, создаем...")
        init_db()

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
    try:
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
        
        active_sellers = []  # Пока пусто, нужно адаптировать функцию
        really_active_sellers = []
        
        return render_template('buyer.html',
                             in_stock=in_stock,
                             in_transit=in_transit,
                             total=len(items_list),
                             active_sellers=really_active_sellers)
    except Exception as e:
        print(f"❌ Ошибка в /buyer: {e}")
        return render_template('buyer.html',
                             in_stock=[],
                             in_transit=[],
                             total=0,
                             active_sellers=[])

# ... (остальные маршруты упрощаем для начала) ...

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    """Вход для продавца"""
    try:
        # Пытаемся очистить старые сессии
        execute_query("SELECT 1 FROM active_sessions LIMIT 1")
        execute_query("DELETE FROM active_sessions WHERE last_activity < NOW() - INTERVAL '8 hours'")
    except:
        pass  # Игнорируем ошибку если таблицы нет
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            seller = execute_query('SELECT * FROM sellers WHERE username = %s', 
                                 (username,), fetchone=True)
            
            if seller and bcrypt.check_password_hash(seller['password_hash'], password):
                # Простой вход без проверки активных сессий
                session_token = secrets.token_hex(32)
                now_utc = datetime.utcnow()
                
                # Удаляем старые сессии
                execute_query('DELETE FROM active_sessions WHERE seller_id = %s', (seller['id'],))
                
                # Создаем новую сессию
                execute_query('''
                INSERT INTO active_sessions (seller_id, session_token, ip_address, user_agent, login_time, last_activity)
                VALUES (%s, %s, %s, %s, %s, %s)
                ''', (
                    seller['id'], 
                    session_token, 
                    request.remote_addr, 
                    request.user_agent.string[:200],
                    now_utc,
                    now_utc
                ))
                
                # Сохраняем в сессии Flask
                session['seller_logged_in'] = True
                session['seller_id'] = seller['id']
                session['seller_username'] = seller['username']
                session['display_name'] = seller.get('display_name') or seller['username']
                session['session_token'] = session_token
                
                return redirect(url_for('seller_dashboard'))
            else:
                return render_template('seller_login.html', error='Неверный логин или пароль')
        except Exception as e:
            print(f"❌ Ошибка входа: {e}")
            return render_template('seller_login.html', error='Ошибка базы данных')
    
    return render_template('seller_login.html')

@app.route('/seller/dashboard')
def seller_dashboard():
    """Панель управления продавца"""
    if not session.get('seller_logged_in'):
        return redirect(url_for('seller_login'))
    
    try:
        items = execute_query('SELECT * FROM items ORDER BY id DESC', fetchall=True)
        items_list = [dict(item) for item in items]
        
        # Статистика
        stats = {
            'total': len(items_list),
            'in_stock': len([i for i in items_list if i['status'] == 'в наличии']),
            'sold': len([i for i in items_list if i['status'] == 'продано']),
            'in_transit': len([i for i in items_list if i['status'] == 'в пути']),
        }
        
        return render_template('seller_dashboard.html',
                             items=items_list,
                             stats=stats,
                             recent_actions=[],
                             active_sellers=[],
                             active_count=0,
                             login_time_local='')
    except Exception as e:
        print(f"❌ Ошибка в dashboard: {e}")
        return render_template('seller_dashboard.html',
                             items=[],
                             stats={'total':0,'in_stock':0,'sold':0,'in_transit':0},
                             recent_actions=[],
                             active_sellers=[],
                             active_count=0,
                             login_time_local='')

@app.route('/seller/add', methods=['POST'])
def add_item():
    """Добавить товар"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        
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
        
        return jsonify({'success': True, 'id': 1})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/update/<int:item_id>', methods=['POST'])
def update_item(item_id):
    """Обновить статус товара"""
    if not session.get('seller_logged_in'):
        return jsonify({'error': 'Нет доступа'}), 401
    
    try:
        data = request.get_json()
        new_status = data['status']
        
        if new_status == 'продано':
            execute_query('''
            UPDATE items SET status = %s, date_sold = %s WHERE id = %s
            ''', (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        elif new_status == 'взял себе':
            execute_query('''
            UPDATE items SET status = %s, date_taken = %s WHERE id = %s
            ''', (new_status, datetime.now().strftime('%Y-%m-%d'), item_id))
        else:
            execute_query('UPDATE items SET status = %s WHERE id = %s', (new_status, item_id))
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца"""
    if session.get('seller_id'):
        try:
            execute_query('DELETE FROM active_sessions WHERE seller_id = %s', (session['seller_id'],))
        except:
            pass
    
    session.clear()
    return redirect(url_for('index'))

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    # Для локальной разработки
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    # На Render - создаем таблицы при импорте
    print("🚀 Запуск на Render, проверяем таблицы...")
    try:
        with app.app_context():
            init_db()
    except Exception as e:
        print(f"⚠️ Предупреждение при инициализации БД: {e}")
