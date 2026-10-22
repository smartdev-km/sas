from datetime import date, datetime

from flask import Blueprint, render_template, request
from sqlalchemy import extract, func

from app import db
from app.decorators import role_required
from app.models import Depense, TransactionBancaire
from app.constants import MOIS_FR
from app.compte_bancaire import _solde_avant

recettes_bp = Blueprint("recettes", __name__, url_prefix="/recettes")

PERIODES_VALIDES = (3, 6, 12)


def _sum(query_result):
    return float(query_result) if query_result is not None else 0.0


def _mois_precedent(mois, annee):
    if mois == 1:
        return 12, annee - 1
    return mois - 1, annee


def _totaux_mois(mois, annee):
    recettes = _sum(
        db.session.query(func.sum(TransactionBancaire.montant))
        .filter(
            TransactionBancaire.sens == "debit",
            extract("year", TransactionBancaire.date) == annee,
            extract("month", TransactionBancaire.date) == mois,
        )
        .scalar()
    )
    depenses = _sum(
        db.session.query(func.sum(Depense.montant))
        .filter(extract("year", Depense.date) == annee, extract("month", Depense.date) == mois)
        .scalar()
    )
    return {"recettes": recettes, "depenses": depenses, "solde": recettes - depenses}


@recettes_bp.route("/")
@role_required("recettes")
def index():
    today = date.today()
    periode = request.args.get("periode", 3, type=int)
    if periode not in PERIODES_VALIDES:
        periode = 3

    mois, annee = today.month, today.year
    lignes_mois = []
    for _ in range(periode):
        totaux = _totaux_mois(mois, annee)
        lignes_mois.append({
            "mois": mois,
            "annee": annee,
            "label": f"{MOIS_FR[mois - 1]} {annee}",
            **totaux,
        })
        mois, annee = _mois_precedent(mois, annee)
    lignes_mois.reverse()

    premier_mois, premiere_annee = lignes_mois[0]["mois"], lignes_mois[0]["annee"]
    solde_ouverture = _solde_avant(date(premiere_annee, premier_mois, 1))

    ligne_ouverture = {
        "label": "Solde d'ouverture",
        "recettes": solde_ouverture,
        "depenses": 0.0,
        "solde": solde_ouverture,
        "est_ouverture": True,
    }
    lignes = [ligne_ouverture] + lignes_mois

    total_recettes = sum(l["recettes"] for l in lignes)
    total_depenses = sum(l["depenses"] for l in lignes)

    return render_template(
        "recettes/index.html",
        lignes=lignes,
        lignes_mois=lignes_mois,
        periode=periode,
        periodes=PERIODES_VALIDES,
        solde_ouverture=solde_ouverture,
        total_recettes=total_recettes,
        total_depenses=total_depenses,
        total_solde=total_recettes - total_depenses,
        periode_label=f"{lignes_mois[0]['label']} – {lignes_mois[-1]['label']}" if lignes_mois else "",
        now=datetime.now(),
    )
