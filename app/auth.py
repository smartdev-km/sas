from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_

from app import db
from app.models import User
from app.constants import SEXES

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin_account:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("presence.confirmer"))

    if request.method == "POST":
        identifiant = request.form.get("identifiant", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            or_(User.username.ilike(identifiant), User.email.ilike(identifiant))
        ).first()

        if user is None or not user.check_password(password):
            flash("Identifiant ou mot de passe incorrect.", "danger")
            return redirect(url_for("auth.login"))

        login_user(user)
        next_page = request.args.get("next")
        if next_page and user.role == "admin":
            return redirect(next_page)
        return redirect(url_for("dashboard.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profil():
    if not current_user.is_admin_account:
        abort(403)

    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        telephone = request.form.get("telephone", "").strip()
        adresse = request.form.get("adresse", "").strip()
        date_naissance = _parse_date(request.form.get("date_naissance"))
        sexe = request.form.get("sexe") or None
        numero_piece_identite = request.form.get("numero_piece_identite", "").strip()

        erreurs = []
        if not nom:
            erreurs.append("Le nom est obligatoire.")
        if sexe and sexe not in SEXES:
            erreurs.append("Le sexe sélectionné est invalide.")

        if username:
            existe = User.query.filter(User.username.ilike(username), User.id != current_user.id).first()
            if existe:
                erreurs.append(f"Le nom d'utilisateur '{username}' est déjà utilisé.")

        if email:
            existe = User.query.filter(User.email.ilike(email), User.id != current_user.id).first()
            if existe:
                erreurs.append(f"L'email '{email}' est déjà utilisé.")

        mot_de_passe_actuel = request.form.get("mot_de_passe_actuel", "")
        nouveau_mot_de_passe = request.form.get("nouveau_mot_de_passe", "")
        confirmation = request.form.get("confirmation_mot_de_passe", "")
        changer_mdp = bool(nouveau_mot_de_passe or confirmation)

        if changer_mdp:
            if not current_user.check_password(mot_de_passe_actuel):
                erreurs.append("Le mot de passe actuel est incorrect.")
            elif len(nouveau_mot_de_passe) < 6:
                erreurs.append("Le nouveau mot de passe doit contenir au moins 6 caractères.")
            elif nouveau_mot_de_passe != confirmation:
                erreurs.append("Les nouveaux mots de passe ne correspondent pas.")

        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("auth/profil.html", sexes=SEXES)

        current_user.nom = nom
        current_user.username = username or None
        current_user.email = email or None
        current_user.telephone = telephone or None
        current_user.adresse = adresse or None
        current_user.date_naissance = date_naissance
        current_user.sexe = sexe
        current_user.numero_piece_identite = numero_piece_identite or None
        if changer_mdp:
            current_user.set_password(nouveau_mot_de_passe)

        db.session.commit()
        flash("Profil mis à jour avec succès.", "success")
        return redirect(url_for("auth.profil"))

    return render_template("auth/profil.html", sexes=SEXES)
