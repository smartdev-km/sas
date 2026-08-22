from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.decorators import role_required, admin_required
from sqlalchemy import func

from app import db
from app.models import TransactionBancaire, CompteBancaireConfig, Depense, Salaire

compte_bancaire_bp = Blueprint("compte_bancaire", __name__, url_prefix="/compte-bancaire")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _config():
    config = CompteBancaireConfig.query.first()
    if not config:
        config = CompteBancaireConfig(solde_initial=0)
        db.session.add(config)
        db.session.commit()
    return config


def _solde_avant(date_limite):
    """Solde cumulé (solde initial + toutes les transactions strictement avant date_limite)."""
    config = _config()
    total_debit = db.session.query(func.coalesce(func.sum(TransactionBancaire.montant), 0)).filter(
        TransactionBancaire.sens == "debit", TransactionBancaire.date < date_limite
    ).scalar()
    total_credit = db.session.query(func.coalesce(func.sum(TransactionBancaire.montant), 0)).filter(
        TransactionBancaire.sens == "credit", TransactionBancaire.date < date_limite
    ).scalar()
    return float(config.solde_initial) + float(total_debit) - float(total_credit)


def _origine_transaction(transaction):
    """Si la transaction a été créée automatiquement depuis une dépense ou un bulletin de
    salaire validé, retourne un libellé décrivant l'origine ; sinon None."""
    if Depense.query.filter_by(transaction_bancaire_id=transaction.id).first():
        return "une dépense"
    if Salaire.query.filter_by(transaction_bancaire_id=transaction.id).first():
        return "un bulletin de salaire"
    return None


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

    if form.get("sens") not in ("debit", "credit"):
        erreurs.append("Le sens (débit/crédit) est invalide.")

    return erreurs


@compte_bancaire_bp.route("/")
@role_required("compte_bancaire")
def liste():
    today = date.today()
    annee = request.args.get("annee", today.year, type=int)
    mois = request.args.get("mois", today.month, type=int)

    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee + 1, 1, 1) if mois == 12 else date(annee, mois + 1, 1)

    transactions = TransactionBancaire.query.filter(
        TransactionBancaire.date >= debut_mois, TransactionBancaire.date < fin_mois
    ).order_by(TransactionBancaire.date, TransactionBancaire.id).all()

    solde_ouverture = _solde_avant(debut_mois)
    solde = solde_ouverture
    total_debit = 0.0
    total_credit = 0.0
    lignes = []
    for t in transactions:
        montant = float(t.montant)
        if t.sens == "debit":
            solde += montant
            total_debit += montant
        else:
            solde -= montant
            total_credit += montant
        lignes.append({"transaction": t, "solde": solde, "origine": _origine_transaction(t)})

    return render_template(
        "compte_bancaire/liste.html",
        lignes=lignes,
        mois=mois,
        annee=annee,
        annees=range(today.year - 2, today.year + 2),
        solde_ouverture=solde_ouverture,
        total_debit=total_debit,
        total_credit=total_credit,
        solde=solde,
        config=_config(),
    )


@compte_bancaire_bp.route("/nouvelle", methods=["POST"])
@role_required("compte_bancaire")
def nouvelle():
    mois = request.form.get("mois", type=int) or date.today().month
    annee = request.form.get("annee", type=int) or date.today().year

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de transaction directement.", "warning")
        return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))

    erreurs = _valider_formulaire(request.form)
    if erreurs:
        for erreur in erreurs:
            flash(erreur, "danger")
    else:
        db.session.add(TransactionBancaire(
            date=_parse_date(request.form.get("date")),
            beneficiaire=request.form.get("beneficiaire", "").strip() or None,
            libelle=request.form.get("libelle", "").strip() or None,
            reference_paiement=request.form.get("reference_paiement", "").strip() or None,
            montant=request.form.get("montant"),
            sens=request.form.get("sens"),
        ))
        db.session.commit()
        flash("Transaction ajoutée.", "success")

    return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))


@compte_bancaire_bp.route("/<int:transaction_id>/modifier", methods=["POST"])
@role_required("compte_bancaire")
def modifier(transaction_id):
    transaction = db.get_or_404(TransactionBancaire, transaction_id)
    mois = request.form.get("mois", type=int) or transaction.date.month
    annee = request.form.get("annee", type=int) or transaction.date.year

    origine = _origine_transaction(transaction)
    if origine:
        flash(f"Cette transaction provient de {origine} validée, elle ne peut être modifiée que depuis ce module.", "warning")
        return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))

    if transaction.valide:
        flash("Cette transaction est validée, elle ne peut plus être modifiée.", "warning")
        return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))

    erreurs = _valider_formulaire(request.form)
    if erreurs:
        for erreur in erreurs:
            flash(erreur, "danger")
    else:
        transaction.date = _parse_date(request.form.get("date"))
        transaction.beneficiaire = request.form.get("beneficiaire", "").strip() or None
        transaction.libelle = request.form.get("libelle", "").strip() or None
        transaction.reference_paiement = request.form.get("reference_paiement", "").strip() or None
        transaction.montant = request.form.get("montant")
        transaction.sens = request.form.get("sens")
        db.session.commit()
        flash("Transaction modifiée.", "success")

    return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))


@compte_bancaire_bp.route("/<int:transaction_id>/supprimer", methods=["POST"])
@role_required("compte_bancaire")
def supprimer(transaction_id):
    transaction = db.get_or_404(TransactionBancaire, transaction_id)
    mois, annee = transaction.date.month, transaction.date.year

    origine = _origine_transaction(transaction)
    if origine:
        flash(f"Cette transaction provient de {origine} validée, elle ne peut être supprimée que depuis ce module.", "warning")
        return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))

    if transaction.valide:
        flash("Cette transaction est validée, elle ne peut plus être supprimée.", "warning")
        return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))

    db.session.delete(transaction)
    db.session.commit()
    flash("Transaction supprimée.", "info")
    return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))


@compte_bancaire_bp.route("/<int:transaction_id>/valider", methods=["POST"])
@admin_required
def valider(transaction_id):
    transaction = db.get_or_404(TransactionBancaire, transaction_id)
    mois, annee = transaction.date.month, transaction.date.year

    if transaction.valide:
        flash("Cette transaction est déjà validée.", "info")
    else:
        transaction.valide = True
        transaction.valide_le = datetime.now()
        db.session.commit()
        flash("Transaction validée. Elle ne peut plus être modifiée ni supprimée.", "success")

    return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))


@compte_bancaire_bp.route("/<int:transaction_id>/devalider", methods=["POST"])
@admin_required
def devalider(transaction_id):
    transaction = db.get_or_404(TransactionBancaire, transaction_id)
    mois, annee = transaction.date.month, transaction.date.year

    origine = _origine_transaction(transaction)
    if origine:
        flash(f"Cette transaction provient de {origine} validée, déverrouillez-la depuis ce module.", "warning")
        return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))

    if not transaction.valide:
        flash("Cette transaction n'est pas validée.", "info")
    else:
        transaction.valide = False
        transaction.valide_le = None
        db.session.commit()
        flash("Transaction déverrouillée, elle peut de nouveau être modifiée.", "success")

    return redirect(url_for("compte_bancaire.liste", mois=mois, annee=annee))


@compte_bancaire_bp.route("/solde-initial", methods=["POST"])
@admin_required
def solde_initial():
    montant_brut = request.form.get("solde_initial", "").strip()
    try:
        montant = float(montant_brut) if montant_brut else 0.0
    except ValueError:
        flash("Le solde initial est invalide.", "danger")
        return redirect(url_for("compte_bancaire.liste"))

    config = _config()
    config.solde_initial = montant
    db.session.commit()
    flash("Solde initial mis à jour.", "success")
    return redirect(url_for("compte_bancaire.liste"))
