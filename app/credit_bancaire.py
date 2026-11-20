from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.decorators import admin_required

from app import db
from app.models import CreditBancaire, TrancheCreditBancaire
from app.fournisseurs import situation_marches_fournisseurs

credit_bancaire_bp = Blueprint("credit_bancaire", __name__, url_prefix="/credit-bancaire")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_montant(value, autoriser_zero=False):
    value = (value or "").strip()
    if not value:
        return 0.0 if autoriser_zero else None
    try:
        montant = float(value)
    except ValueError:
        return None
    if montant < 0 or (montant == 0 and not autoriser_zero):
        return None
    return montant


def _valider_banque(form):
    erreurs = []
    if not form.get("banque", "").strip():
        erreurs.append("Le nom de la banque est obligatoire.")
    if _parse_montant(form.get("financement_total")) is None:
        erreurs.append("Le financement total doit être un nombre positif.")
    return erreurs


def _valider_tranche(form):
    erreurs = []
    if not _parse_date(form.get("date")):
        erreurs.append("La date est invalide ou manquante.")
    if _parse_montant(form.get("montant_tranche")) is None:
        erreurs.append("Le montant de la tranche doit être un nombre positif.")
    if _parse_montant(form.get("frais_prealable"), autoriser_zero=True) is None:
        erreurs.append("Les frais préalables doivent être un nombre positif ou nul.")
    return erreurs


@credit_bancaire_bp.route("/")
@admin_required
def liste():
    credits = CreditBancaire.query.order_by(CreditBancaire.banque).all()

    total_financement = sum(float(c.financement_total) for c in credits)
    total_verse = sum(c.total_tranches_versees() for c in credits)
    total_frais = sum(c.total_frais_prealables() for c in credits)
    total_net = sum(c.total_net_verse() for c in credits)
    pourcentage_global = (total_verse / total_financement * 100) if total_financement else 0.0

    return render_template(
        "credit_bancaire/liste.html",
        credits=credits,
        total_financement=total_financement,
        total_verse=total_verse,
        total_frais=total_frais,
        total_net=total_net,
        pourcentage_global=pourcentage_global,
        now=datetime.now(),
        **situation_marches_fournisseurs(),
    )


@credit_bancaire_bp.route("/nouveau", methods=["GET", "POST"])
@admin_required
def nouveau():
    if request.method == "POST":
        erreurs = _valider_banque(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("credit_bancaire/form.html", credit=None, form=request.form)

        credit = CreditBancaire(
            banque=request.form.get("banque", "").strip(),
            financement_total=_parse_montant(request.form.get("financement_total")),
            notes=request.form.get("notes", "").strip() or None,
            cree_par_id=current_user.id,
        )
        db.session.add(credit)
        db.session.commit()
        flash(f"« {credit.banque} » ajoutée.", "success")
        return redirect(url_for("credit_bancaire.detail", credit_id=credit.id))

    return render_template("credit_bancaire/form.html", credit=None, form={})


@credit_bancaire_bp.route("/<int:credit_id>")
@admin_required
def detail(credit_id):
    credit = db.get_or_404(CreditBancaire, credit_id)
    return render_template("credit_bancaire/detail.html", credit=credit, today=datetime.now().date().isoformat())


@credit_bancaire_bp.route("/<int:credit_id>/modifier", methods=["GET", "POST"])
@admin_required
def modifier(credit_id):
    credit = db.get_or_404(CreditBancaire, credit_id)

    if request.method == "POST":
        erreurs = _valider_banque(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("credit_bancaire/form.html", credit=credit, form=request.form)

        credit.banque = request.form.get("banque", "").strip()
        credit.financement_total = _parse_montant(request.form.get("financement_total"))
        credit.notes = request.form.get("notes", "").strip() or None
        db.session.commit()
        flash("Banque modifiée.", "success")
        return redirect(url_for("credit_bancaire.detail", credit_id=credit.id))

    form = {
        "banque": credit.banque,
        "financement_total": credit.financement_total,
        "notes": credit.notes or "",
    }
    return render_template("credit_bancaire/form.html", credit=credit, form=form)


@credit_bancaire_bp.route("/<int:credit_id>/supprimer", methods=["POST"])
@admin_required
def supprimer(credit_id):
    credit = db.get_or_404(CreditBancaire, credit_id)
    banque = credit.banque

    for tranche in list(credit.tranches):
        db.session.delete(tranche)
    db.session.delete(credit)
    db.session.commit()
    flash(f"« {banque} » supprimée.", "info")

    return redirect(url_for("credit_bancaire.liste"))


@credit_bancaire_bp.route("/<int:credit_id>/tranches/nouvelle", methods=["GET", "POST"])
@admin_required
def tranche_nouvelle(credit_id):
    credit = db.get_or_404(CreditBancaire, credit_id)

    if request.method == "POST":
        erreurs = _valider_tranche(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("credit_bancaire/tranche_form.html", credit=credit, tranche=None, form=request.form)

        db.session.add(TrancheCreditBancaire(
            credit_id=credit.id,
            date=_parse_date(request.form.get("date")),
            montant_tranche=_parse_montant(request.form.get("montant_tranche")),
            frais_prealable=_parse_montant(request.form.get("frais_prealable"), autoriser_zero=True),
            notes=request.form.get("notes", "").strip() or None,
        ))
        db.session.commit()
        flash("Tranche ajoutée.", "success")
        return redirect(url_for("credit_bancaire.detail", credit_id=credit.id))

    form = {"date": datetime.now().date().isoformat()}
    return render_template("credit_bancaire/tranche_form.html", credit=credit, tranche=None, form=form)


@credit_bancaire_bp.route("/tranches/<int:tranche_id>/modifier", methods=["GET", "POST"])
@admin_required
def tranche_modifier(tranche_id):
    tranche = db.get_or_404(TrancheCreditBancaire, tranche_id)
    credit = tranche.credit

    if request.method == "POST":
        erreurs = _valider_tranche(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("credit_bancaire/tranche_form.html", credit=credit, tranche=tranche, form=request.form)

        tranche.date = _parse_date(request.form.get("date"))
        tranche.montant_tranche = _parse_montant(request.form.get("montant_tranche"))
        tranche.frais_prealable = _parse_montant(request.form.get("frais_prealable"), autoriser_zero=True)
        tranche.notes = request.form.get("notes", "").strip() or None
        db.session.commit()
        flash("Tranche modifiée.", "success")
        return redirect(url_for("credit_bancaire.detail", credit_id=credit.id))

    form = {
        "date": tranche.date.isoformat(),
        "montant_tranche": tranche.montant_tranche,
        "frais_prealable": tranche.frais_prealable,
        "notes": tranche.notes or "",
    }
    return render_template("credit_bancaire/tranche_form.html", credit=credit, tranche=tranche, form=form)


@credit_bancaire_bp.route("/tranches/<int:tranche_id>/supprimer", methods=["POST"])
@admin_required
def tranche_supprimer(tranche_id):
    tranche = db.get_or_404(TrancheCreditBancaire, tranche_id)
    credit_id = tranche.credit_id
    db.session.delete(tranche)
    db.session.commit()
    flash("Tranche supprimée.", "info")

    return redirect(url_for("credit_bancaire.detail", credit_id=credit_id))
