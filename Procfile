web: gunicorn app:app
release: python -c "from app import ensure_database_exists; ensure_database_exists()"
