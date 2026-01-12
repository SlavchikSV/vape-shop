import os
import sqlite3
import subprocess
import shutil
import json
from datetime import datetime
import atexit
import signal
import threading
import time
from pathlib import Path
from flask_bcrypt import Bcrypt

class GitHubDBManager:
    def __init__(self, db_name='shop.db'):
        self.db_name = db_name
        self.local_db_path = db_name
        self.backup_dir = 'db_backups'
        self.last_save_time = None
        self.is_saving = False
        self.save_queue = []
        
        # Создаем директории
        os.makedirs(self.backup_dir, exist_ok=True)
        
        print(f"🔄 GitHub DB Manager инициализирован для {db_name}")
        print(f"📁 Локальный путь: {self.local_db_path}")
        print(f"📂 Бэкапы: {self.backup_dir}")
        
        # Инициализируем Git если нужно
        self.init_git()
        
        # Регистрируем обработчики для сохранения при выходе
        atexit.register(self.on_exit)
        signal.signal(signal.SIGTERM, self.on_signal)
        signal.signal(signal.SIGINT, self.on_signal)
        
        # Запускаем обработчик очереди
        self.start_queue_processor()
    
    def init_git(self):
        """Инициализируем Git если нужно"""
        try:
            # Проверяем, инициализирован ли Git
            if not os.path.exists('.git'):
                subprocess.run(['git', 'init'], check=True, capture_output=True)
                print("✅ Git репозиторий инициализирован")
            
            # Проверяем конфигурацию пользователя
            result = subprocess.run(['git', 'config', 'user.email'], 
                                  capture_output=True, text=True)
            if not result.stdout.strip():
                subprocess.run(['git', 'config', 'user.email', 'slavaveselov2006@gmail.com'], 
                             check=True)
                subprocess.run(['git', 'config', 'user.name', 'SlavchikSV'], 
                             check=True)
                print("✅ Git пользователь настроен")
                
        except Exception as e:
            print(f"⚠️ Ошибка инициализации Git: {e}")
    
    def start_queue_processor(self):
        """Запускаем обработчик очереди сохранения"""
        def queue_processor():
            while True:
                if self.save_queue and not self.is_saving:
                    self.process_save_queue()
                time.sleep(1)
        
        thread = threading.Thread(target=queue_processor, daemon=True)
        thread.start()
        print("✅ Обработчик очереди сохранения запущен")
    
    def process_save_queue(self):
        """Обрабатывает очередь сохранения"""
        if self.is_saving or not self.save_queue:
            return
        
        self.is_saving = True
        try:
            # Берем первую задачу из очереди
            reason = self.save_queue.pop(0)
            self._save_to_github(reason)
        except Exception as e:
            print(f"❌ Ошибка обработки очереди: {e}")
        finally:
            self.is_saving = False
    
    def on_exit(self):
        """Сохраняем БД при выходе из приложения"""
        print("💾 Сохраняю базу данных перед выходом...")
        self.save_db_to_github("exit_backup")
    
    def on_signal(self, signum, frame):
        """Обработчик сигналов"""
        print(f"📶 Получен сигнал {signum}, сохраняю базу...")
        self.save_db_to_github("signal_backup")
        exit(0)
    
    def init_or_restore_db(self):
        """Инициализация или восстановление БД из GitHub"""
        print("🔄 Проверяю наличие базы данных...")
        
        # Шаг 1: Проверяем локальную базу
        if os.path.exists(self.db_name):
            print(f"✅ База уже существует локально: {self.db_name}")
            return True
        
        # Шаг 2: Пробуем загрузить из GitHub
        if self.load_db_from_github():
            print("✅ База загружена из GitHub")
            return True
        
        # Шаг 3: Если нет в GitHub, создаем новую
        print("🆕 Создаю новую базу данных...")
        self.create_new_database()
        
        # Шаг 4: Сохраняем новую базу в GitHub
        self.save_db_to_github("initial_creation")
        
        return True
    
    def load_db_from_github(self):
        """Загружаем последнюю версию БД из GitHub"""
        try:
            print("📥 Пробую загрузить базу из GitHub...")
            
            # 1. Пробуем pull из GitHub
            print("⬇️  Загружаю изменения из GitHub...")
            pull_result = subprocess.run(
                ['git', 'pull', 'origin', 'main', '--no-rebase'],
                capture_output=True, text=True
            )
            
            if pull_result.returncode != 0:
                print(f"⚠️ Git pull не удался: {pull_result.stderr}")
            
            # 2. Проверяем, есть ли файл базы
            if os.path.exists(self.db_name):
                print(f"✅ База найдена локально: {self.db_name}")
                return True
            
            # 3. Ищем в истории Git
            print("🔍 Ищу базу в истории Git...")
            result = subprocess.run(
                ['git', 'log', '--oneline', '--name-only', '--', self.db_name],
                capture_output=True, text=True
            )
            
            if self.db_name in result.stdout:
                # Восстанавливаем файл из Git истории
                print("📦 Восстанавливаю базу из истории Git...")
                subprocess.run(['git', 'checkout', 'HEAD', '--', self.db_name], 
                             check=True, capture_output=True)
                
                if os.path.exists(self.db_name):
                    print(f"✅ База восстановлена из Git истории: {self.db_name}")
                    return True
            
            print("❌ База не найдена ни локально, ни в GitHub")
            return False
            
        except Exception as e:
            print(f"❌ Ошибка загрузки базы: {e}")
            return False
    
    def save_db_to_github(self, reason="auto_save"):
        """Сохраняем БД в GitHub (ставим в очередь)"""
        if reason not in self.save_queue:
            self.save_queue.append(reason)
            print(f"📋 Сохранение [{reason}] добавлено в очередь. В очереди: {len(self.save_queue)}")
        return True
    
    def _save_to_github(self, reason="auto_save"):
        """Фактическое сохранение БД в GitHub"""
        if not os.path.exists(self.db_name):
            print(f"⚠️ Файл базы {self.db_name} не существует, пропускаю сохранение")
            return False
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 1. Создаем локальный бэкап
            backup_file = f"backup_{timestamp}_{reason}.db"
            backup_path = os.path.join(self.backup_dir, backup_file)
            shutil.copy2(self.db_name, backup_path)
            print(f"📁 Создан локальный бэкап: {backup_file}")
            
            # 2. Добавляем базу в Git
            print("➕ Добавляю базу в Git...")
            add_result = subprocess.run(
                ['git', 'add', self.db_name],
                capture_output=True, text=True
            )
            
            if add_result.returncode != 0:
                print(f"⚠️ Ошибка добавления в Git: {add_result.stderr}")
            
            # 3. Коммитим изменения
            commit_msg = f"DB Backup [{reason}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            print(f"💾 Коммит: {commit_msg}")
            
            commit_result = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                capture_output=True, text=True
            )
            
            if commit_result.returncode != 0:
                # Если коммит не нужен (нет изменений)
                print("📝 Нет изменений для коммита")
                
                # Но все равно пушим, чтобы синхронизировать
                push_needed = True
            else:
                push_needed = True
                print("✅ Коммит создан")
            
            # 4. Пушим в GitHub если нужно
            if push_needed:
                print("🚀 Отправляю изменения в GitHub...")
                push_result = subprocess.run(
                    ['git', 'push', 'origin', 'main'],
                    capture_output=True, text=True
                )
                
                if push_result.returncode == 0:
                    print(f"✅ База сохранена в GitHub: {commit_msg}")
                    self.last_save_time = datetime.now()
                    
                    # Очищаем старые бэкапы (оставляем последние 3)
                    self.cleanup_old_backups(keep_last=3)
                    
                    return True
                else:
                    print(f"❌ Ошибка push: {push_result.stderr}")
                    return False
            else:
                print("✅ Изменения уже синхронизированы с GitHub")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка сохранения базы: {e}")
            return False
    
    def cleanup_old_backups(self, keep_last=3):
        """Удаляем старые бэкапы"""
        try:
            backups = sorted([
                f for f in os.listdir(self.backup_dir) 
                if f.startswith('backup_') and f.endswith('.db')
            ])
            
            if len(backups) > keep_last:
                for old_backup in backups[:-keep_last]:
                    os.remove(os.path.join(self.backup_dir, old_backup))
                    print(f"🗑️ Удален старый бэкап: {old_backup}")
        except Exception as e:
            print(f"⚠️ Ошибка очистки бэкапов: {e}")
    
    def create_new_database(self):
        """Создает новую базу данных с базовой структурой"""
        bcrypt = Bcrypt()
        
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
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
        print(f"✅ Новая база создана: {self.db_name}")
    
    def start_auto_save(self, interval_minutes=3):
        """Запускает автоматическое сохранение каждые N минут"""
        def auto_save_worker():
            print(f"⏰ Авто-сохранение запущено (каждые {interval_minutes} минут)")
            while True:
                time.sleep(interval_minutes * 60)
                print("🔄 Автоматическое сохранение базы...")
                self.save_db_to_github("auto_save")
        
        thread = threading.Thread(target=auto_save_worker, daemon=True)
        thread.start()
    
def get_db_connection(self):
    """Возвращает соединение с базой данных"""
    conn = sqlite3.connect(self.db_name)
    conn.row_factory = sqlite3.Row
    
    # Создаем кастомный класс для соединения
    class CustomConnection:
        def __init__(self, conn, db_manager):
            self._conn = conn
            self.db_manager = db_manager
        
        def __getattr__(self, name):
            # Делегируем все остальные методы оригинальному соединению
            return getattr(self._conn, name)
        
        def commit(self):
            # Вызываем оригинальный commit
            self._conn.commit()
            # Ставим в очередь сохранение после коммита
            self.db_manager.save_db_to_github("after_commit")
        
        def cursor(self):
            return self._conn.cursor()
        
        def close(self):
            return self._conn.close()
        
        def execute(self, *args, **kwargs):
            return self._conn.execute(*args, **kwargs)
        
        def executemany(self, *args, **kwargs):
            return self._conn.executemany(*args, **kwargs)
        
        def executescript(self, *args, **kwargs):
            return self._conn.executescript(*args, **kwargs)
        
        def fetchone(self, *args, **kwargs):
            return self._conn.fetchone(*args, **kwargs) if hasattr(self._conn, 'fetchone') else None
        
        def fetchall(self, *args, **kwargs):
            return self._conn.fetchall(*args, **kwargs) if hasattr(self._conn, 'fetchall') else None
    
    return CustomConnection(conn, self)

# Глобальный экземпляр менеджера БД
db_manager = GitHubDBManager()
