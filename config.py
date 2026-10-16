import os

basedir = os.path.abspath(os.path.dirname(__file__))

_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    if os.environ.get("RENDER"):
        # Sur Render, tant qu'aucun DATABASE_URL (base PostgreSQL) n'est configuré,
        # on retombe sur une base SQLite temporaire pour permettre de tester l'app.
        # Cette base est réinitialisée à chaque redéploiement.
        _database_url = "sqlite:////tmp/sas_test.db"
    else:
        _database_url = "postgresql://sas_user:sas_password@localhost:5432/sas_db"
# Render (et Heroku) fournissent une URL commençant par "postgres://", que les
# versions récentes de SQLAlchemy refusent : il faut "postgresql://".
if _database_url.startswith("postgres://"):
    _database_url = _database_url.replace("postgres://", "postgresql://", 1)
# Forcer explicitement le driver psycopg2 : sans suffixe "+psycopg2", certaines
# versions de SQLAlchemy retiennent par défaut le driver psycopg (v3), qui
# n'est pas installé ici, et le démarrage plante avec "No module named 'psycopg'".
if _database_url.startswith("postgresql://"):
    _database_url = _database_url.replace("postgresql://", "postgresql+psycopg2://", 1)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-moi-en-production")
    SQLALCHEMY_DATABASE_URI = _database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
