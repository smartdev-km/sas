from datetime import date
from decimal import Decimal

from flask import Blueprint, render_template
from app.decorators import role_required
from sqlalchemy import func, extract

from app import db
from app.models import Depense, Fournisseur, FactureFournisseur, Salaire, SuiviConsommable

dashboard_bp = Blueprint("dashboard", __name__)

MOIS_FR = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
    "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
]


def _sum(query_result):
    return float(query_result) if query_result is not None else 0.0


def _last_12_months():
    """Retourne une liste de (mois, annee) des 12 derniers mois, du plus ancien au plus récent."""
    today = date.today()
    months = []
    year, month = today.year, today.month
    for _ in range(12):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@role_required("dashboard")
def index():
    today = date.today()

    total_depenses = _sum(db.session.query(func.sum(Depense.montant)).scalar())

    depenses_mois = _sum(
        db.session.query(func.sum(Depense.montant))
        .filter(extract("year", Depense.date) == today.year, extract("month", Depense.date) == today.month)
        .scalar()
    )

    nb_fournisseurs = db.session.query(func.count(Fournisseur.id)).filter(Fournisseur.actif.is_(True)).scalar() or 0

    masse_salariale_mois = _sum(
        db.session.query(func.sum(Salaire.montant))
        .filter(Salaire.annee == today.year, Salaire.mois == today.month)
        .scalar()
    )

    consommables_mois = _sum(
        db.session.query(func.sum(SuiviConsommable.montant))
        .filter(SuiviConsommable.annee == today.year, SuiviConsommable.mois == today.month)
        .scalar()
    )
    nb_consommables_mois = (
        db.session.query(func.count(SuiviConsommable.id))
        .filter(SuiviConsommable.annee == today.year, SuiviConsommable.mois == today.month)
        .scalar() or 0
    )
    nb_consommables_payes = (
        db.session.query(func.count(SuiviConsommable.id))
        .filter(SuiviConsommable.annee == today.year, SuiviConsommable.mois == today.month, SuiviConsommable.paye.is_(True))
        .scalar() or 0
    )

    months = _last_12_months()
    labels = [f"{MOIS_FR[m - 1]} {y}" for y, m in months]

    depenses_par_mois = []
    consommables_par_mois = []
    for y, m in months:
        d = _sum(
            db.session.query(func.sum(Depense.montant))
            .filter(extract("year", Depense.date) == y, extract("month", Depense.date) == m)
            .scalar()
        )
        c = _sum(
            db.session.query(func.sum(SuiviConsommable.montant))
            .filter(SuiviConsommable.annee == y, SuiviConsommable.mois == m)
            .scalar()
        )
        depenses_par_mois.append(d)
        consommables_par_mois.append(c)

    categories_rows = (
        db.session.query(Depense.categorie, func.sum(Depense.montant))
        .group_by(Depense.categorie)
        .all()
    )
    categories_labels = [c or "Non catégorisé" for c, _ in categories_rows]
    categories_valeurs = [float(v) for _, v in categories_rows]

    total_consommables_tous_mois = _sum(db.session.query(func.sum(SuiviConsommable.montant)).scalar())
    if total_consommables_tous_mois:
        categories_labels.append("Consommables")
        categories_valeurs.append(total_consommables_tous_mois)

    kpis = {
        "total_depenses": total_depenses,
        "depenses_mois": depenses_mois,
        "nb_fournisseurs": nb_fournisseurs,
        "masse_salariale_mois": masse_salariale_mois,
        "consommables_mois": consommables_mois,
        "nb_consommables_mois": nb_consommables_mois,
        "nb_consommables_payes": nb_consommables_payes,
    }

    chart_data = {
        "labels": labels,
        "depenses": depenses_par_mois,
        "consommables": consommables_par_mois,
        "categories_labels": categories_labels,
        "categories_valeurs": categories_valeurs,
    }

    dernieres_depenses = Depense.query.order_by(Depense.date.desc(), Depense.id.desc()).limit(10).all()
    dernieres_factures_fournisseurs = (
        FactureFournisseur.query.join(Fournisseur)
        .order_by(FactureFournisseur.date_facture.desc(), FactureFournisseur.id.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "dashboard/index.html", kpis=kpis, chart_data=chart_data,
        dernieres_depenses=dernieres_depenses, dernieres_factures_fournisseurs=dernieres_factures_fournisseurs,
    )
