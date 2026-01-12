# github_backup.py
import os
import time
import sqlite3
import subprocess
import threading
from datetime import datetime
import shutil
import atexit
import signal

class GitHubBackup:
    def __init__(self, db_path='shop.db', backup_dir='backups'):
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.is_backing_up = False
        self.last_backup_time = 0
        self.backup_interval = 300  # 5 минут
        
        # Создаем директорию для бэкапов
        os.makedirs(backup_dir, exist_ok=True)
        
        print("✅ GitHub Backup инициализирован")
    
    def create_backup_file(self):
        """Создает резервную копию базы данных"""
        if not os.path.exists(self.db_path):
            return None
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{self.backup_dir}/shop_backup_{timestamp}.db"
        
        # Копируем базу
        shutil.copy2(self.db_path, backup_path)
        print(f"📁 Создана локальная копия: {backup_path}")
        
        return backup_path
    
    def commit_to_git(self, backup_file):
        """Добавляет файл в Git и отправляет в GitHub"""
        try:
            # Добавляем файл в Git
            subprocess.run(['git', 'add', backup_file], 
                         check=True, capture_output=True)
            
            # Коммитим
            commit_msg = f"Бэкап базы данных {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            subprocess.run(['git', 'commit', '-m', commit_msg, backup_file], 
                         check=True, capture_output=True)
            
            # Пушим в GitHub (только backup файл)
            result = subprocess.run(['git', 'push'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ Бэкап отправлен в GitHub: {backup_file}")
                
                # Удаляем старые локальные бэкапы (оставляем последние 3)
                self.cleanup_old_backups()
                return True
            else:
                print(f"⚠️ Ошибка Git: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка при работе с Git: {e}")
            return False
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return False
    
    def cleanup_old_backups(self):
        """Удаляет старые локальные бэкапы"""
        try:
            backups = sorted([
                f for f in os.listdir(self.backup_dir) 
                if f.startswith('shop_backup_') and f.endswith('.db')
            ])
            
            # Оставляем последние 3 бэкапа
            if len(backups) > 3:
                for old_backup in backups[:-3]:
                    os.remove(os.path.join(self.backup_dir, old_backup))
                    print(f"🗑️ Удален старый бэкап: {old_backup}")
        except Exception as e:
            print(f"⚠️ Ошибка очистки бэкапов: {e}")
    
    def backup_now(self, force=False):
        """Создает бэкап сейчас"""
        if self.is_backing_up:
            print("⏳ Бэкап уже выполняется...")
            return False
            
        current_time = time.time()
        if not force and (current_time - self.last_backup_time) < 60:
            print("⏳ Слишком частые бэкапы, пропускаю...")
            return False
            
        self.is_backing_up = True
        
        try:
            # Создаем локальную копию
            backup_file = self.create_backup_file()
            if not backup_file:
                print("⚠️ База данных не найдена для бэкапа")
                return False
            
            # Отправляем в GitHub
            success = self.commit_to_git(backup_file)
            
            if success:
                self.last_backup_time = current_time
                return True
            else:
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при создании бэкапа: {e}")
            return False
        finally:
            self.is_backing_up = False
    
    def auto_backup_loop(self):
        """Автоматическое создание бэкапов каждые N минут"""
        print(f"🔄 Авто-бэкап запущен (интервал: {self.backup_interval//60} минут)")
        
        while True:
            time.sleep(self.backup_interval)
            
            # Проверяем, есть ли изменения в базе
            if self.has_db_changes():
                print("🔄 Обнаружены изменения в БД, создаю бэкап...")
                self.backup_now()
            else:
                print("⏭️ Нет изменений в БД, пропускаю бэкап")
    
    def has_db_changes(self):
        """Проверяет, были ли изменения в базе данных"""
        if not os.path.exists(self.db_path):
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Проверяем время последнего изменения
            cursor.execute("SELECT MAX(created_at) FROM items")
            result = cursor.fetchone()[0]
            
            cursor.execute("SELECT MAX(created_at) FROM sellers")
            result2 = cursor.fetchone()[0]
            
            conn.close()
            
            # Если есть хоть одна запись
            return result is not None or result2 is not None
            
        except:
            return False
    
    def restore_latest(self):
        """Восстанавливает последний бэкап из GitHub"""
        try:
            print("🔄 Восстанавливаю последний бэкап из GitHub...")
            
            # Pull из GitHub
            result = subprocess.run(['git', 'pull'], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"⚠️ Ошибка при pull: {result.stderr}")
                return False
            
            # Ищем последний бэкап
            backups = sorted([
                f for f in os.listdir(self.backup_dir) 
                if f.startswith('shop_backup_') and f.endswith('.db')
            ])
            
            if backups:
                latest_backup = os.path.join(self.backup_dir, backups[-1])
                
                # Копируем бэкап как основную базу
                shutil.copy2(latest_backup, self.db_path)
                print(f"✅ База восстановлена из: {latest_backup}")
                return True
            else:
                print("⚠️ Нет бэкапов для восстановления")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка восстановления: {e}")
            return False

# Глобальный экземпляр
backup_manager = GitHubBackup()

def start_backup_scheduler():
    """Запускает автоматическое резервное копирование в отдельном потоке"""
    thread = threading.Thread(target=backup_manager.auto_backup_loop, daemon=True)
    thread.start()
    print("✅ Планировщик бэкапов запущен")
    
    # Сохраняем при выходе
    def save_on_exit():
        print("💾 Создаю финальный бэкап перед выходом...")
        backup_manager.backup_now(force=True)
    
    atexit.register(save_on_exit)
    
    # Обработчик сигналов
    def signal_handler(signum, frame):
        print(f"📶 Получен сигнал {signum}, создаю бэкап...")
        backup_manager.backup_now(force=True)
        exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

# Функции для ручного управления
def manual_backup():
    """Ручное создание бэкапа"""
    return backup_manager.backup_now(force=True)

def manual_restore():
    """Ручное восстановление"""
    return backup_manager.restore_latest()

if __name__ == '__main__':
    # Тестирование
    start_backup_scheduler()
    
    # Ручной бэкап
    manual_backup()
    
    # Оставляем программу запущенной
    while True:
        time.sleep(1)
