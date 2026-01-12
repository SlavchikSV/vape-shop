# init_db.py - Альтернативный скрипт для создания базы
from db_manager import db_manager
import sys

def main():
    print("🔄 Инициализация базы данных...")
    
    choice = input("Вы хотите:\n1. Создать новую базу\n2. Восстановить из GitHub\nВыберите (1/2): ")
    
    if choice == '1':
        db_manager.create_new_database()
        print("✅ Новая база создана")
        
        save = input("Сохранить новую базу в GitHub? (y/n): ")
        if save.lower() == 'y':
            db_manager.save_db_to_github("manual_init")
            print("✅ База сохранена в GitHub")
    
    elif choice == '2':
        if db_manager.load_db_from_github():
            print("✅ База восстановлена из GitHub")
        else:
            print("❌ Не удалось восстановить базу")
    
    else:
        print("❌ Неверный выбор")

if __name__ == '__main__':
    main()
