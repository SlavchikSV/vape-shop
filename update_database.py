#!/usr/bin/env python3
"""
Скрипт для обновления структуры базы данных
Запустите на Render через Console (если есть доступ) или добавьте в build command
"""

import os
import psycopg2

def update_database():
    """Добавить недостающие столбцы в базу данных"""
    print("🔄 Обновляю структуру базы данных...")
    
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL не найден")
        return
    
    try:
        conn = psycopg2.connect(database_url, sslmode='require')
        cursor = conn.cursor()
        
        # 1. Добавляем столбец is_wholesale если его нет
        cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='items' AND column_name='is_wholesale'
        """)
        
        if not cursor.fetchone():
            print("📦 Добавляю столбец is_wholesale в таблицу items...")
            cursor.execute('ALTER TABLE items ADD COLUMN is_wholesale BOOLEAN DEFAULT FALSE')
            print("✅ Столбец is_wholesale добавлен")
        else:
            print("✅ Столбец is_wholesale уже существует")
        
        # 2. Добавляем столбец reserved_until если его нет
        cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='items' AND column_name='reserved_until'
        """)
        
        if not cursor.fetchone():
            print("📅 Добавляю столбец reserved_until в таблицу items...")
            cursor.execute('ALTER TABLE items ADD COLUMN reserved_until TEXT')
            print("✅ Столбец reserved_until добавлен")
        else:
            print("✅ Столбец reserved_until уже существует")
        
        # 3. Добавляем столбец is_wholesale в shipments если его нет
        cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='shipments' AND column_name='is_wholesale'
        """)
        
        if not cursor.fetchone():
            print("📦 Добавляю столбец is_wholesale в таблицу shipments...")
            cursor.execute('ALTER TABLE shipments ADD COLUMN is_wholesale BOOLEAN DEFAULT FALSE')
            print("✅ Столбец is_wholesale добавлен в shipments")
        else:
            print("✅ Столбец is_wholesale уже существует в shipments")
        
        # 4. Добавляем столбец sold_items в shipments если его нет
        cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='shipments' AND column_name='sold_items'
        """)
        
        if not cursor.fetchone():
            print("💰 Добавляю столбец sold_items в таблицу shipments...")
            cursor.execute('ALTER TABLE shipments ADD COLUMN sold_items INTEGER DEFAULT 0')
            print("✅ Столбец sold_items добавлен")
        else:
            print("✅ Столбец sold_items уже существует")
        
        conn.commit()
        print("🎉 Структура базы данных успешно обновлена!")
        
        # Показываем текущую структуру
        print("\n📊 Структура таблицы items:")
        cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='items' ORDER BY ordinal_position")
        for column in cursor.fetchall():
            print(f"  - {column[0]}: {column[1]}")
        
        print("\n📊 Структура таблицы shipments:")
        cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='shipments' ORDER BY ordinal_position")
        for column in cursor.fetchall():
            print(f"  - {column[0]}: {column[1]}")
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении базы данных: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    update_database()
