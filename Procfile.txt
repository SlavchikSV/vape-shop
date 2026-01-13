web: gunicorn app:app
release: python -c "from app import init_db; init_db()"
