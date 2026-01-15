#!/usr/bin/env python3
"""
Скрипт для обновления базы данных - добавление поддержки изображений
Запустите: python update_db_images.py
"""

import psycopg2
import os

def update_database_for_images():
    """Обновить структуру базы данных для поддержки изображений"""
    
    print("🖼️ Обновление базы данных для поддержки изображений...")
    
    # Получаем URL базы данных из переменных окружения
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Для Render - используем SSL
        conn = psycopg2.connect(database_url, sslmode='require')
    else:
        # Для локальной разработки
        conn = psycopg2.connect(
            database="shop",
            user="postgres",
            password="postgres",
            host="localhost",
            port="5432"
        )
    
    cursor = conn.cursor()
    
    try:
        # Проверяем существование столбца image_url в items
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='items' AND column_name='image_url'
        """)
        
        if not cursor.fetchone():
            print("📷 Добавляю столбец image_url...")
            cursor.execute('ALTER TABLE items ADD COLUMN image_url TEXT')
            print("✅ Столбец image_url успешно добавлен")
        else:
            print("✅ Столбец image_url уже существует")
        
        conn.commit()
        print("🎉 База данных успешно обновлена для поддержки изображений!")
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении базы данных: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    update_database_for_images()
