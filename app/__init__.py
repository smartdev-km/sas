from flask import Flask, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv

from config import Config

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "warning"


@login_manager.unauthorized_handler
def unauthorized():
    flash(login_manager.login_message, login_manager.login_message_category)
    if request.path.startswith("/employe") or request.path.startswith("/presence/confirmer"):
        return redirect(url_for("employe_auth.login"))
    return redirect(url_for("auth.login"))


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app.models import User, Employe

    @login_manager.user_loader
    def load_user(user_id):
        kind, _, raw_id = user_id.partition(":")
        if kind == "user":
            return db.session.get(User, int(raw_id))
        if kind == "employe":
            return db.session.get(Employe, int(raw_id))
        return None

    from app.auth import auth_bp
    from app.dashboard import dashboard_bp
    from app.depenses import depenses_bp
    from app.compte_bancaire import compte_bancaire_bp
    from app.fournisseurs import fournisseurs_bp
    from app.salaires import salaires_bp
    from app.rapports import rapports_bp
    from app.appareils import appareils_bp
    from app.consommables import consommables_bp
    from app.employe_auth import employe_auth_bp
    from app.presence import presence_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(depenses_bp)
    app.register_blueprint(compte_bancaire_bp)
    app.register_blueprint(fournisseurs_bp)
    app.register_blueprint(salaires_bp)
    app.register_blueprint(rapports_bp)
    app.register_blueprint(appareils_bp)
    app.register_blueprint(consommables_bp)
    app.register_blueprint(employe_auth_bp)
    app.register_blueprint(presence_bp)

    from app import cli
    cli.register(app)

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        with app.app_context():
            db.create_all()
            if not User.query.first():
                admin = User(nom="Admin", email="admin@sas.local", role="admin")
                admin.set_password("admin123")
                db.session.add(admin)
                db.session.commit()

    app.jinja_env.filters["kmf"] = format_kmf
    app.jinja_env.filters["nombre"] = format_nombre
    app.jinja_env.filters["kmf2"] = format_kmf2
    app.jinja_env.filters["nombre2"] = format_nombre2

    return app


def format_kmf(value):
    return format_nombre(value) + " KMF"


def format_nombre(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0
    return f"{value:,.0f}".replace(",", " ")


def format_kmf2(value):
    return format_nombre2(value) + " KMF"


def format_nombre2(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0
    entier, _, decimales = f"{value:,.2f}".partition(".")
    return entier.replace(",", " ") + "," + decimales
