import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import secrets
import atexit
import signal
import threading
import time
from functools import wraps

# Импортируем наш менеджер БД
from db_manager import db_manager

# ==================== НАСТРОЙКА ПРИЛОЖЕНИЯ ====================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this-in-production')
bcrypt = Bcrypt(app)

# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ====================
def init_app():
    """Инициализация приложения"""
    print("=" * 50)
    print("🚀 ЗАПУСК ПРИЛОЖЕНИЯ НА RENDER")
    print("=" * 50)
    
    # Инициализируем или восстанавливаем базу из GitHub
    if db_manager.init_or_restore_db():
        print("✅ База данных готова")
    else:
        print("❌ Не удалось инициализировать базу данных")
        # Создаем новую базу в любом случае
        db_manager.create_new_database()
    
    # Запускаем авто-сохранение каждые 3 минуты
    db_manager.start_auto_save(interval_minutes=3)
    
    print("✅ Приложение инициализировано")
    print(f"📊 База данных: {os.path.abspath('shop.db')}")
    print("=" * 50)

# Запускаем инициализацию при импорте
init_app()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_db():
    """Получаем соединение с базой через менеджер"""
    return db_manager.get_db_connection()

def log_action(seller_id, action_type, item_id=None, details=""):
    """Логирование действия"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO action_log (seller_id, action_type, item_id, details, ip_address, user_agent)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (seller_id, action_type, item_id, details, 
          request.remote_addr, request.user_agent.string[:200]))
    
    conn.commit()
    conn.close()
    
    # Ставим авто-сохранение в очередь после важного действия
    if action_type in ['add_item', 'update_item', 'sale', 'add_shipment', 'update_shipment']:
        threading.Thread(
            target=db_manager.save_db_to_github,
            args=(f"action_{action_type}",),
            daemon=True
        ).start()
    
    print(f"📝 Действие: {seller_id} - {action_type}")

def seller_required(f):
    """Декоратор для проверки авторизации продавца"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('seller_logged_in'):
            return redirect(url_for('seller_login', expired='true'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== МАРШРУТЫ ====================
@app.route('/')
def index():
    return redirect(url_for('buyer'))

@app.route('/buyer')
def buyer():
    """Страница для покупателей"""
    conn = get_db()
    
    # Только товары в наличии
    items = conn.execute('''
        SELECT id, name, sell_price, manual_price, status, date_arrived 
        FROM items 
        WHERE status = 'в наличии'
        ORDER BY date_arrived DESC
    ''').fetchall()
    
    conn.close()
    
    items_list = [dict(item) for item in items]
    for item in items_list:
        item['display_price'] = item['manual_price'] or item['sell_price']
    
    return render_template('buyer.html', in_stock=items_list, total=len(items_list))

@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    """Вход для продавца"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        seller = conn.execute('SELECT * FROM sellers WHERE username = ?', 
                             (username,)).fetchone()
        conn.close()
        
        if seller and bcrypt.check_password_hash(seller['password_hash'], password):
            # Создаем сессию
            session_token = secrets.token_hex(32)
            session['seller_logged_in'] = True
            session['seller_id'] = seller['id']
            session['seller_username'] = seller['username']
            session['display_name'] = seller['display_name'] or seller['username']
            session['session_token'] = session_token
            
            # Логируем вход
            log_action(seller['id'], 'login')
            
            # Сохраняем в GitHub после входа
            threading.Thread(
                target=db_manager.save_db_to_github,
                args=("after_login",),
                daemon=True
            ).start()
            
            return redirect(url_for('seller_dashboard'))
        else:
            flash('Неверный логин или пароль', 'danger')
    
    return render_template('seller_login.html')

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца"""
    if session.get('seller_id'):
        log_action(session['seller_id'], 'logout')
        # Сохраняем перед выходом
        db_manager.save_db_to_github("before_logout")
    
    session.clear()
    return redirect(url_for('index'))

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    """Панель управления продавца"""
    conn = get_db()
    
    # Все товары
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
    
    # Статистика
    stats = {
        'total': conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],
        'in_stock': conn.execute("SELECT COUNT(*) FROM items WHERE status = 'в наличии'").fetchone()[0],
        'in_transit': conn.execute("SELECT COUNT(*) FROM items WHERE status = 'в пути'").fetchone()[0],
        'reserved': conn.execute("SELECT COUNT(*) FROM items WHERE status = 'зарезервировано'").fetchone()[0],
        'sold': conn.execute("SELECT COUNT(*) FROM items WHERE status = 'продано'").fetchone()[0],
        'personal': conn.execute("SELECT COUNT(*) FROM items WHERE status = 'взял себе'").fetchone()[0],
    }
    
    conn.close()
    
    items_list = [dict(item) for item in items]
    return render_template('seller_dashboard.html', 
                         items=items_list, 
                         stats=stats,
                         login_time_local=datetime.now().strftime('%H:%M'))

# ==================== API ДЛЯ AJAX ====================
@app.route('/seller/add', methods=['POST'])
@seller_required
def add_item():
    """Добавить товар"""
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO items (name, cost_price, sell_price, status, date_arrived, manual_price)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            float(data['cost_price']),
            float(data['sell_price']),
            data['status'],
            datetime.now().strftime('%Y-%m-%d'),
            float(data['sell_price'])
        ))
        
        item_id = cursor.lastrowid
        
        # Транзакция покупки
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
        
        # Логируем и сохраняем в GitHub
        log_action(session['seller_id'], 'add_item', item_id, 
                  f'Добавлен товар: {data["name"]}')
        
        return jsonify({'success': True, 'id': item_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/update/<int:item_id>', methods=['POST'])
@seller_required
def update_item(item_id):
    """Обновить статус товара"""
    try:
        data = request.get_json()
        new_status = data['status']
        
        conn = get_db()
        
        # Получаем текущий статус
        item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            conn.close()
            return jsonify({'error': 'Товар не найден'}), 404
        
        old_status = item['status']
        
        # Обновляем статус
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
        
        query = f'UPDATE items SET status = ?{date_field} WHERE id = ?'
        
        if date_field and date_value:
            conn.execute(query, (new_status, date_value, item_id))
        else:
            conn.execute(query, (new_status, item_id))
        
        # Транзакция продажи
        if old_status != 'продано' and new_status == 'продано':
            sell_price = item['manual_price'] or item['sell_price']
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
        
        conn.commit()
        conn.close()
        
        # Логируем и сохраняем в GitHub
        log_action(session['seller_id'], 'update_item', item_id, 
                  f'Статус изменен: {old_status} -> {new_status}')
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/shipments/create_with_items', methods=['POST'])
@seller_required
def create_shipment_with_items():
    """Создать поставку с товарами"""
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
            0,
            'в пути'
        ))
        
        shipment_id = cursor.lastrowid
        
        # Добавляем товары
        items = data.get('items', [])
        for item_data in items:
            cursor.execute('''
            INSERT INTO items (name, cost_price, sell_price, status, shipment_id, date_arrived, manual_price)
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
        
        # Обновляем счетчик
        cursor.execute('''
        UPDATE shipments 
        SET total_items = ?
        WHERE id = ?
        ''', (len(items), shipment_id))
        
        conn.commit()
        conn.close()
        
        # Логируем и сохраняем в GitHub
        log_action(session['seller_id'], 'add_shipment', 
                  details=f'Создана поставка {shipment_number} с {len(items)} товарами')
        
        return jsonify({
            'success': True, 
            'shipment_id': shipment_id,
            'shipment_number': shipment_number,
            'added_count': len(items)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/seller/keepalive')
@seller_required
def keepalive():
    """Поддержание активности сессии"""
    return jsonify({'success': True})

# ==================== API ДЛЯ УПРАВЛЕНИЯ БАЗОЙ ====================
@app.route('/admin/manual_save', methods=['POST'])
@seller_required
def manual_save():
    """Ручное сохранение базы в GitHub"""
    try:
        success = db_manager.save_db_to_github("manual_save")
        if success:
            return jsonify({'success': True, 'message': 'База сохранена в GitHub'})
        else:
            return jsonify({'success': False, 'error': 'Ошибка сохранения'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/restore_db', methods=['POST'])
@seller_required
def restore_db():
    """Восстановление базы из GitHub"""
    try:
        success = db_manager.load_db_from_github()
        if success:
            return jsonify({'success': True, 'message': 'База восстановлена из GitHub'})
        else:
            return jsonify({'success': False, 'error': 'Не удалось восстановить базу'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/db_status')
@seller_required
def db_status():
    """Статус базы данных"""
    db_exists = os.path.exists('shop.db')
    db_size = os.path.getsize('shop.db') if db_exists else 0
    
    return jsonify({
        'exists': db_exists,
        'size_kb': round(db_size / 1024, 2),
        'last_save': db_manager.last_save_time if hasattr(db_manager, 'last_save_time') else None
    })

# ==================== ЗАПУСК СЕРВЕРА ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
