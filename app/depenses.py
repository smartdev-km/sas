from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.decorators import role_required, admin_required
from sqlalchemy import func

from app import db
from app.models import Depense, TransactionBancaire
from app.constants import CATEGORIES_DEPENSE

depenses_bp = Blueprint("depenses", __name__, url_prefix="/depenses")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@depenses_bp.route("/")
@role_required("depenses")
def liste():
    date_debut = _parse_date(request.args.get("date_debut"))
    date_fin = _parse_date(request.args.get("date_fin"))
    categorie = request.args.get("categorie") or ""
    beneficiaire = request.args.get("beneficiaire") or ""
    page = request.args.get("page", 1, type=int)

    query = Depense.query

    if date_debut:
        query = query.filter(Depense.date >= date_debut)
    if date_fin:
        query = query.filter(Depense.date <= date_fin)
    if categorie:
        query = query.filter(Depense.categorie == categorie)
    if beneficiaire:
        query = query.filter(Depense.beneficiaire.ilike(f"%{beneficiaire}%"))

    total_filtre = query.with_entities(func.coalesce(func.sum(Depense.montant), 0)).scalar()

    pagination = query.order_by(Depense.date.desc(), Depense.id.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template(
        "depenses/liste.html",
        depenses=pagination.items,
        pagination=pagination,
        categories=CATEGORIES_DEPENSE,
        total_filtre=float(total_filtre),
        filtres={
            "date_debut": request.args.get("date_debut", ""),
            "date_fin": request.args.get("date_fin", ""),
            "categorie": categorie,
            "beneficiaire": beneficiaire,
        },
    )


@depenses_bp.route("/nouvelle", methods=["GET", "POST"])
@role_required("depenses")
def nouvelle():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de dépense, seulement les valider.", "warning")
        return redirect(url_for("depenses.liste"))

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "depenses/form.html",
                categories=CATEGORIES_DEPENSE,
                depense=None,
                form=request.form,
            )

        mode_paiement = request.form.get("mode_paiement") or "cash"
        depense = Depense(
            date=_parse_date(request.form.get("date")),
            montant=request.form.get("montant"),
            categorie=request.form.get("categorie") or None,
            beneficiaire=request.form.get("beneficiaire", "").strip() or None,
            description=request.form.get("description") or None,
            mode_paiement=mode_paiement,
            libelle_bancaire=request.form.get("libelle_bancaire", "").strip() or None if mode_paiement == "compte_bancaire" else None,
            reference_paiement=request.form.get("reference_paiement", "").strip() or None if mode_paiement == "compte_bancaire" else None,
        )
        db.session.add(depense)
        db.session.commit()
        flash("Dépense ajoutée avec succès.", "success")
        return redirect(url_for("depenses.liste"))

    return render_template(
        "depenses/form.html",
        categories=CATEGORIES_DEPENSE,
        depense=None,
        form={},
    )


@depenses_bp.route("/<int:depense_id>/modifier", methods=["GET", "POST"])
@role_required("depenses")
def modifier(depense_id):
    depense = db.get_or_404(Depense, depense_id)

    if depense.valide:
        flash("Cette dépense est validée, elle ne peut plus être modifiée.", "warning")
        return redirect(url_for("depenses.liste"))

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "depenses/form.html",
                categories=CATEGORIES_DEPENSE,
                depense=depense,
                form=request.form,
            )

        mode_paiement = request.form.get("mode_paiement") or "cash"
        depense.date = _parse_date(request.form.get("date"))
        depense.montant = request.form.get("montant")
        depense.categorie = request.form.get("categorie") or None
        depense.beneficiaire = request.form.get("beneficiaire", "").strip() or None
        depense.description = request.form.get("description") or None
        depense.mode_paiement = mode_paiement
        depense.libelle_bancaire = request.form.get("libelle_bancaire", "").strip() or None if mode_paiement == "compte_bancaire" else None
        depense.reference_paiement = request.form.get("reference_paiement", "").strip() or None if mode_paiement == "compte_bancaire" else None
        db.session.commit()
        flash("Dépense modifiée avec succès.", "success")
        return redirect(url_for("depenses.liste"))

    return render_template(
        "depenses/form.html",
        categories=CATEGORIES_DEPENSE,
        depense=depense,
        form={
            "date": depense.date.isoformat() if depense.date else "",
            "montant": depense.montant,
            "categorie": depense.categorie or "",
            "beneficiaire": depense.beneficiaire or "",
            "description": depense.description or "",
            "mode_paiement": depense.mode_paiement,
            "libelle_bancaire": depense.libelle_bancaire or "",
            "reference_paiement": depense.reference_paiement or "",
        },
    )


@depenses_bp.route("/<int:depense_id>/supprimer", methods=["POST"])
@role_required("depenses")
def supprimer(depense_id):
    depense = db.get_or_404(Depense, depense_id)

    if depense.valide:
        flash("Cette dépense est validée, elle ne peut plus être supprimée.", "danger")
        return redirect(url_for("depenses.liste"))

    db.session.delete(depense)
    db.session.commit()
    flash("Dépense supprimée.", "info")
    return redirect(url_for("depenses.liste"))


@depenses_bp.route("/<int:depense_id>/valider", methods=["POST"])
@admin_required
def valider(depense_id):
    depense = db.get_or_404(Depense, depense_id)

    if depense.valide:
        flash("Cette dépense est déjà validée.", "info")
    else:
        depense.valide = True
        depense.valide_le = datetime.now()

        if depense.mode_paiement == "compte_bancaire" and not depense.transaction_bancaire_id:
            transaction = TransactionBancaire(
                date=depense.date,
                beneficiaire=depense.beneficiaire,
                libelle=depense.libelle_bancaire or depense.description,
                reference_paiement=depense.reference_paiement,
                montant=depense.montant,
                sens="credit",
                valide=True,
                valide_le=datetime.now(),
            )
            db.session.add(transaction)
            db.session.flush()
            depense.transaction_bancaire_id = transaction.id
            flash("Dépense validée et transaction ajoutée au Compte Bancaire.", "success")
        else:
            flash("Dépense validée. Elle ne peut plus être modifiée ni supprimée.", "success")

        db.session.commit()

    return redirect(url_for("depenses.liste"))


@depenses_bp.route("/<int:depense_id>/devalider", methods=["POST"])
@admin_required
def devalider(depense_id):
    depense = db.get_or_404(Depense, depense_id)

    if not depense.valide:
        flash("Cette dépense n'est pas validée.", "info")
        return redirect(url_for("depenses.liste"))

    if depense.transaction_bancaire_id:
        transaction = TransactionBancaire.query.get(depense.transaction_bancaire_id)
        depense.transaction_bancaire_id = None
        db.session.flush()
        if transaction:
            db.session.delete(transaction)

    depense.valide = False
    depense.valide_le = None
    db.session.commit()
    flash("Dépense déverrouillée, elle peut de nouveau être modifiée.", "success")
    return redirect(url_for("depenses.liste"))


def _valider_formulaire(form):
    erreurs = []

    date_valeur = _parse_date(form.get("date"))
    if not date_valeur:
        erreurs.append("La date est invalide ou manquante.")

    montant_brut = form.get("montant", "").strip()
    try:
        montant = float(montant_brut)
        if montant <= 0:
            erreurs.append("Le montant doit être supérieur à 0.")
    except (TypeError, ValueError):
        erreurs.append("Le montant est invalide.")

    if form.get("mode_paiement") not in ("cash", "compte_bancaire"):
        erreurs.append("Le mode de paiement est invalide.")

    return erreurs
