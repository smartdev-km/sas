web: sh -c 'if [ -n "$DATABASE_URL" ]; then flask db upgrade; fi; gunicorn run:app'
