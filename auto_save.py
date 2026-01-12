# auto_save.py
import time
import os
import shutil
import threading

def auto_save_database():
    """Автоматическое сохранение базы данных каждые 5 минут"""
    while True:
        time.sleep(300)  # 5 минут
        
        if os.path.exists('shop.db'):
            try:
                if not os.path.exists('/data'):
                    os.makedirs('/data', exist_ok=True)
                
                shutil.copy2('shop.db', '/data/shop.db')
                print(f"💾 Автосохранение: {time.ctime()}")
            except Exception as e:
                print(f"⚠️ Ошибка автосохранения: {e}")

def start_auto_save():
    """Запуск автосохранения в отдельном потоке"""
    thread = threading.Thread(target=auto_save_database, daemon=True)
    thread.start()
    print("✅ Автосохранение запущено (каждые 5 минут)")

if __name__ == '__main__':
    start_auto_save()
    # Бесконечный цикл
    while True:
        time.sleep(1)
