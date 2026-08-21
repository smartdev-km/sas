import os

basedir = os.path.abspath(os.path.dirname(__file__))

_database_url = os.environ.get(
    "DATABASE_URL",
    "postgresql://sas_user:sas_password@localhost:5432/sas_db",
)
# Render (et Heroku) fournissent une URL commençant par "postgres://", que les
# versions récentes de SQLAlchemy refusent : il faut "postgresql://".
if _database_url.startswith("postgres://"):
    _database_url = _database_url.replace("postgres://", "postgresql://", 1)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-moi-en-production")
    SQLALCHEMY_DATABASE_URI = _database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
