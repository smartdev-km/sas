from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import extract

from app import db
from app.models import EvenementAgenda
from app.decorators import role_required, admin_required
from app.constants import MOIS_FR

agenda_bp = Blueprint("agenda", __name__, url_prefix="/agenda")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_heure(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


@agenda_bp.route("/")
@role_required("agenda")
def liste():
    today = date.today()
    annee = request.args.get("annee", today.year, type=int)
    mois = request.args.get("mois", today.month, type=int)

    evenements = (
        EvenementAgenda.query.filter(
            extract("year", EvenementAgenda.date) == annee,
            extract("month", EvenementAgenda.date) == mois,
        )
        .order_by(EvenementAgenda.date, EvenementAgenda.heure_debut)
        .all()
    )

    return render_template(
        "agenda/liste.html",
        evenements=evenements,
        mois=mois,
        annee=annee,
        annees=range(today.year - 2, today.year + 2),
        mois_fr=MOIS_FR,
        mois_label=f"{MOIS_FR[mois - 1]} {annee}",
        today=today,
    )


@agenda_bp.route("/nouveau", methods=["POST"])
@role_required("agenda")
def nouveau():
    mois = request.form.get("mois", type=int) or date.today().month
    annee = request.form.get("annee", type=int) or date.today().year

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter d'événement, seulement les consulter.", "warning")
        return redirect(url_for("agenda.liste", mois=mois, annee=annee))

    titre = request.form.get("titre", "").strip()
    date_evenement = _parse_date(request.form.get("date"))

    if not titre:
        flash("Le titre est obligatoire.", "danger")
    elif not date_evenement:
        flash("La date est invalide ou manquante.", "danger")
    else:
        db.session.add(EvenementAgenda(
            titre=titre,
            date=date_evenement,
            heure_debut=_parse_heure(request.form.get("heure_debut")),
            heure_fin=_parse_heure(request.form.get("heure_fin")),
            lieu=request.form.get("lieu", "").strip() or None,
            description=request.form.get("description", "").strip() or None,
            cree_par_id=current_user.id,
        ))
        db.session.commit()
        flash("Événement ajouté à l'agenda.", "success")
        mois, annee = date_evenement.month, date_evenement.year

    return redirect(url_for("agenda.liste", mois=mois, annee=annee))


@agenda_bp.route("/<int:evenement_id>/modifier", methods=["POST"])
@role_required("agenda")
def modifier(evenement_id):
    evenement = db.get_or_404(EvenementAgenda, evenement_id)
    mois, annee = evenement.date.month, evenement.date.year

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas modifier un événement.", "warning")
        return redirect(url_for("agenda.liste", mois=mois, annee=annee))

    titre = request.form.get("titre", "").strip()
    date_evenement = _parse_date(request.form.get("date"))

    if not titre:
        flash("Le titre est obligatoire.", "danger")
    elif not date_evenement:
        flash("La date est invalide ou manquante.", "danger")
    else:
        evenement.titre = titre
        evenement.date = date_evenement
        evenement.heure_debut = _parse_heure(request.form.get("heure_debut"))
        evenement.heure_fin = _parse_heure(request.form.get("heure_fin"))
        evenement.lieu = request.form.get("lieu", "").strip() or None
        evenement.description = request.form.get("description", "").strip() or None
        db.session.commit()
        flash("Événement modifié.", "success")
        mois, annee = date_evenement.month, date_evenement.year

    return redirect(url_for("agenda.liste", mois=mois, annee=annee))


@agenda_bp.route("/<int:evenement_id>/supprimer", methods=["POST"])
@role_required("agenda")
def supprimer(evenement_id):
    evenement = db.get_or_404(EvenementAgenda, evenement_id)
    mois, annee = evenement.date.month, evenement.date.year

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas supprimer un événement.", "warning")
        return redirect(url_for("agenda.liste", mois=mois, annee=annee))

    db.session.delete(evenement)
    db.session.commit()
    flash("Événement supprimé.", "info")
    return redirect(url_for("agenda.liste", mois=mois, annee=annee))


@agenda_bp.route("/<int:evenement_id>/marquer-vu", methods=["POST"])
@admin_required
def marquer_vu(evenement_id):
    evenement = db.get_or_404(EvenementAgenda, evenement_id)
    evenement.vu_par_admin = not evenement.vu_par_admin
    db.session.commit()
    return redirect(url_for("agenda.liste", mois=evenement.date.month, annee=evenement.date.year))


@agenda_bp.route("/<int:evenement_id>/annuler", methods=["POST"])
@admin_required
def annuler(evenement_id):
    evenement = db.get_or_404(EvenementAgenda, evenement_id)
    evenement.annule = not evenement.annule
    db.session.commit()
    flash(f"Événement {'annulé' if evenement.annule else 'réactivé'}.", "info")
    return redirect(url_for("agenda.liste", mois=evenement.date.month, annee=evenement.date.year))
