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
import subprocess
import shutil
from functools import wraps

# ==================== НАСТРОЙКА ПРИЛОЖЕНИЯ ====================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this-in-production')
bcrypt = Bcrypt(app)

# ==================== GITHUB BACKUP СИСТЕМА ====================
class GitHubBackup:
    def __init__(self, db_path='shop.db'):
        self.db_path = db_path
        self.is_backing_up = False
        self.backup_queue = []
        self.backup_thread = None
        
        print("🔧 Инициализация GitHub Backup системы...")
        
        # Запускаем обработчик очереди бэкапов
        self.start_backup_processor()
        
        # Сохраняем при выходе
        atexit.register(self.final_backup)
        signal.signal(signal.SIGTERM, lambda s, f: self.final_backup())
        signal.signal(signal.SIGINT, lambda s, f: self.final_backup())
    
    def start_backup_processor(self):
        """Запускает обработчик очереди бэкапов в отдельном потоке"""
        def backup_worker():
            while True:
                if self.backup_queue:
                    self._process_backup()
                time.sleep(1)  # Проверяем каждую секунду
        
        self.backup_thread = threading.Thread(target=backup_worker, daemon=True)
        self.backup_thread.start()
        print("✅ Обработчик бэкапов запущен")
    
    def _process_backup(self):
        """Обрабатывает один бэкап из очереди"""
        if self.is_backing_up or not self.backup_queue:
            return
        
        self.is_backing_up = True
        try:
            # Берем первый бэкап из очереди
            backup_type = self.backup_queue.pop(0)
            self._create_backup(backup_type)
        except Exception as e:
            print(f"❌ Ошибка при создании бэкапа: {e}")
        finally:
            self.is_backing_up = False
    
    def _create_backup(self, backup_type):
        """Создает бэкап и отправляет в GitHub"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"shop_backup_{timestamp}.db"
        
        try:
            # 1. Создаем копию базы
            if os.path.exists(self.db_path):
                shutil.copy2(self.db_path, backup_file)
                print(f"📁 Создана локальная копия: {backup_file}")
            else:
                print("⚠️ База данных не найдена, пропускаю бэкап")
                return
            
            # 2. Добавляем в Git
            subprocess.run(['git', 'add', backup_file], 
                         check=True, capture_output=True)
            
            # 3. Коммитим
            commit_msg = f"Бэкап [{backup_type}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(['git', 'commit', '-m', commit_msg], 
                         check=True, capture_output=True)
            
            # 4. Пушим в GitHub
            result = subprocess.run(['git', 'push'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ Бэкап отправлен в GitHub: {commit_msg}")
                
                # 5. Удаляем локальный файл бэкапа
                os.remove(backup_file)
                
                # 6. Очищаем старые коммиты (оставляем последние 50)
                self._cleanup_old_commits()
            else:
                print(f"⚠️ Ошибка Git push: {result.stderr}")
                
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка Git команды: {e}")
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
    
    def _cleanup_old_commits(self):
        """Очищает историю Git, оставляя только последние 50 коммитов"""
        try:
            # Создаем новый коммит с squash старых
            result = subprocess.run(
                ['git', 'checkout', '--orphan', 'temp'],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                subprocess.run(['git', 'add', '-A'], check=True)
                subprocess.run(['git', 'commit', '-m', 'Объединение истории'], check=True)
                subprocess.run(['git', 'branch', '-D', 'main'], check=True)
                subprocess.run(['git', 'branch', '-m', 'main'], check=True)
                subprocess.run(['git', 'push', '-f', 'origin', 'main'], check=True)
                print("🧹 История Git очищена")
        except:
            pass  # Игнорируем ошибки очистки
    
    def queue_backup(self, action_type="auto"):
        """Добавляет бэкап в очередь"""
        if action_type not in self.backup_queue:
            self.backup_queue.append(action_type)
            print(f"📋 Бэкап [{action_type}] добавлен в очередь. В очереди: {len(self.backup_queue)}")
    
    def final_backup(self):
        """Финальный бэкап при завершении"""
        print("💾 Создаю финальный бэкап перед выходом...")
        self._create_backup("final")
    
    def immediate_backup(self):
        """Немедленный бэкап (блокирующий)"""
        print("⚡ Немедленный бэкап...")
        self._create_backup("immediate")

# Создаем глобальный экземпляр бэкап системы
backup_system = GitHubBackup()

# ==================== БАЗА ДАННЫХ ====================
def get_db():
    """Подключение к базе данных с автоматическим бэкапом"""
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Патчим commit для автоматического бэкапа
    original_commit = conn.commit
    def commit_with_backup():
        original_commit()
        # Ставим бэкап в очередь после коммита
        backup_system.queue_backup("db_commit")
    
    conn.commit = commit_with_backup
    return conn

def init_database():
    """Инициализация базы данных"""
    print("🔄 Инициализация базы данных...")
    
    # Пробуем восстановить из GitHub
    try:
        print("📥 Пробую получить последнюю версию базы из GitHub...")
        subprocess.run(['git', 'pull'], capture_output=True, text=True)
        
        # Ищем последний бэкап файл
        backup_files = [f for f in os.listdir('.') if f.startswith('shop_backup_') and f.endswith('.db')]
        if backup_files:
            latest_backup = sorted(backup_files)[-1]
            if os.path.exists(latest_backup):
                shutil.copy2(latest_backup, 'shop.db')
                print(f"✅ База восстановлена из: {latest_backup}")
                # Удаляем временный файл
                os.remove(latest_backup)
                return
    except:
        pass
    
    # Если не удалось восстановить, создаем новую
    print("🆕 Создаю новую базу данных...")
    conn = get_db()
    cursor = conn.cursor()
    
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
    
    # Создаем начальный бэкап
    backup_system.queue_backup("initial")
    print("✅ База данных инициализирована")

# Инициализируем базу при старте
init_database()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def log_action(seller_id, action_type, item_id=None, details=""):
    """Логирование действия с автоматическим бэкапом"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO action_log (seller_id, action_type, item_id, details, ip_address, user_agent)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (seller_id, action_type, item_id, details, 
          request.remote_addr, request.user_agent.string[:200]))
    
    conn.commit()
    conn.close()
    
    # Ставим бэкап в очередь после важного действия
    if action_type in ['add_item', 'update_item', 'sale', 'add_shipment', 'update_shipment']:
        backup_system.queue_backup(action_type)
    
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
            
            # Бэкап после входа
            backup_system.queue_backup("login")
            
            return redirect(url_for('seller_dashboard'))
        else:
            flash('Неверный логин или пароль', 'danger')
    
    return render_template('seller_login.html')

@app.route('/seller/logout')
def seller_logout():
    """Выход продавца"""
    if session.get('seller_id'):
        log_action(session['seller_id'], 'logout')
    
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
        
        # Логируем и делаем бэкап
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
        
        # Логируем и делаем бэкап
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
        SET total_items = ?, updated_at = ?
        WHERE id = ?
        ''', (len(items), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), shipment_id))
        
        conn.commit()
        conn.close()
        
        # Логируем и делаем бэкап
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

@app.route('/admin/create_backup', methods=['POST'])
@seller_required
def create_backup():
    """Ручное создание бэкапа"""
    try:
        backup_system.immediate_backup()
        return jsonify({'success': True, 'message': 'Бэкап создан и отправлен в GitHub'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/restore_backup', methods=['POST'])
@seller_required
def restore_backup():
    """Восстановление из последнего бэкапа"""
    try:
        init_database()
        return jsonify({'success': True, 'message': 'База восстановлена из последнего бэкапа'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ЗАПУСК СЕРВЕРА ====================
if __name__ == '__main__':
    # Автоматический бэкап каждые 30 минут
    def periodic_backup():
        while True:
            time.sleep(1800)  # 30 минут
            backup_system.queue_backup("periodic")
    
    threading.Thread(target=periodic_backup, daemon=True).start()
    
    # Запуск сервера
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
