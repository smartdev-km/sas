from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import Employe, ConnexionLog
from app.constants import SEXES

employe_auth_bp = Blueprint("employe_auth", __name__, url_prefix="/employe")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _log_evenement(employe_id, type_evenement):
    db.session.add(ConnexionLog(
        employe_id=employe_id,
        type_evenement=type_evenement,
        adresse_ip=request.remote_addr,
    ))
    db.session.commit()


@employe_auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin_account:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("presence.confirmer"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        employe = Employe.query.filter(Employe.email.isnot(None), Employe.email.ilike(email)).first()

        if employe is None or not employe.actif or not employe.check_password(password):
            flash("Email ou mot de passe incorrect.", "danger")
            return redirect(url_for("employe_auth.login"))

        login_user(employe)
        _log_evenement(employe.id, "login")
        return redirect(url_for("presence.confirmer"))

    return render_template("employe_auth/login.html")


@employe_auth_bp.route("/logout")
@login_required
def logout():
    employe_id = current_user.id
    logout_user()
    _log_evenement(employe_id, "logout")
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("employe_auth.login"))


@employe_auth_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profil():
    if current_user.is_admin_account:
        abort(403)

    if request.method == "POST":
        telephone = request.form.get("telephone", "").strip()
        email = request.form.get("email", "").strip()
        adresse = request.form.get("adresse", "").strip()
        date_naissance = _parse_date(request.form.get("date_naissance"))
        sexe = request.form.get("sexe") or None
        numero_piece_identite = request.form.get("numero_piece_identite", "").strip()

        erreurs = []
        if sexe and sexe not in SEXES:
            erreurs.append("Le sexe sélectionné est invalide.")
        if not email:
            erreurs.append("L'email est obligatoire (il sert d'identifiant de connexion).")
        else:
            existe = Employe.query.filter(
                Employe.email.ilike(email), Employe.id != current_user.id
            ).first()
            if existe:
                erreurs.append(f"L'email '{email}' est déjà utilisé par un autre employé.")

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
            return render_template("employe_auth/profil.html", sexes=SEXES)

        current_user.telephone = telephone or None
        current_user.email = email
        current_user.adresse = adresse or None
        current_user.date_naissance = date_naissance
        current_user.sexe = sexe
        current_user.numero_piece_identite = numero_piece_identite or None
        if changer_mdp:
            current_user.set_password(nouveau_mot_de_passe)

        # Si cet employé a aussi un compte comptable/secrétaire (Salaires → Employés →
        # Accès), on garde les coordonnées / l'identité civile synchronisées.
        if current_user.compte_utilisateur:
            compte = current_user.compte_utilisateur
            compte.telephone = telephone or None
            compte.adresse = adresse or None
            compte.date_naissance = date_naissance
            compte.sexe = sexe
            compte.numero_piece_identite = numero_piece_identite or None

        db.session.commit()
        flash("Profil mis à jour avec succès.", "success")
        return redirect(url_for("employe_auth.profil"))

    return render_template("employe_auth/profil.html", sexes=SEXES)
