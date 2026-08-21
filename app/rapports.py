from datetime import date, datetime

from flask import Blueprint, render_template, request
from sqlalchemy import func, extract

from app import db
from app.decorators import role_required
from app.models import Depense, Salaire, Fournisseur, FactureFournisseur, Employe, SuiviConsommable, Consommable, TransactionBancaire
from app.constants import MOIS_FR, STATUTS_SALAIRE
from app.presence import calculer_presence_mensuelle
from app.compte_bancaire import _solde_avant

rapports_bp = Blueprint("rapports", __name__, url_prefix="/rapports")


def _sum(query_result):
    return float(query_result) if query_result is not None else 0.0


def _mois_precedent(mois, annee):
    if mois == 1:
        return 12, annee - 1
    return mois - 1, annee


def _solde_fin_mois(mois, annee):
    debut = date(annee, mois, 1)
    fin = date(annee + 1, 1, 1) if mois == 12 else date(annee, mois + 1, 1)
    solde = _solde_avant(debut)
    transactions = TransactionBancaire.query.filter(
        TransactionBancaire.date >= debut, TransactionBancaire.date < fin
    ).all()
    for t in transactions:
        montant = float(t.montant)
        solde += montant if t.sens == "debit" else -montant
    return solde


def _totaux_mois(mois, annee):
    total_depenses = _sum(
        db.session.query(func.sum(Depense.montant))
        .filter(extract("year", Depense.date) == annee, extract("month", Depense.date) == mois)
        .scalar()
    )
    masse_salariale = _sum(
        db.session.query(func.sum(Salaire.montant))
        .filter(Salaire.mois == mois, Salaire.annee == annee)
        .scalar()
    )
    total_consommables = _sum(
        db.session.query(func.sum(SuiviConsommable.montant))
        .filter(SuiviConsommable.mois == mois, SuiviConsommable.annee == annee)
        .scalar()
    )
    solde_compte = _solde_fin_mois(mois, annee)
    return {
        "depenses": total_depenses,
        "masse_salariale": masse_salariale,
        "consommables": total_consommables,
        "solde_compte": solde_compte,
    }


def _variation(valeur_actuelle, valeur_precedente):
    ecart = valeur_actuelle - valeur_precedente
    if valeur_precedente:
        pourcentage = round(ecart / abs(valeur_precedente) * 100, 1)
    else:
        pourcentage = None
    return {"ecart": ecart, "pourcentage": pourcentage}


@rapports_bp.route("/")
@role_required("rapports")
def index():
    today = date.today()
    annee = request.args.get("annee", today.year, type=int)
    mois = request.args.get("mois", today.month, type=int)

    filtre_depenses = (extract("year", Depense.date) == annee, extract("month", Depense.date) == mois)

    total_depenses = _sum(db.session.query(func.sum(Depense.montant)).filter(*filtre_depenses).scalar())
    nb_depenses = db.session.query(func.count(Depense.id)).filter(*filtre_depenses).scalar() or 0

    depenses_par_categorie_rows = (
        db.session.query(Depense.categorie, func.sum(Depense.montant))
        .filter(*filtre_depenses)
        .group_by(Depense.categorie)
        .order_by(func.sum(Depense.montant).desc())
        .all()
    )
    depenses_par_categorie = [
        {
            "label": categorie or "Non catégorisé",
            "montant": float(montant),
            "pourcentage": round(float(montant) / total_depenses * 100, 1) if total_depenses else 0,
        }
        for categorie, montant in depenses_par_categorie_rows
    ]

    # Suivi de la compte bancaire du mois
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee + 1, 1, 1) if mois == 12 else date(annee, mois + 1, 1)

    transactions_bancaires_mois = (
        TransactionBancaire.query.filter(
            TransactionBancaire.date >= debut_mois, TransactionBancaire.date < fin_mois
        ).order_by(TransactionBancaire.date, TransactionBancaire.id).all()
    )
    solde_ouverture = _solde_avant(debut_mois)
    solde_compte = solde_ouverture
    total_debit = 0.0
    total_credit = 0.0
    lignes_bancaires = []
    for t in transactions_bancaires_mois:
        montant = float(t.montant)
        if t.sens == "debit":
            solde_compte += montant
            total_debit += montant
        else:
            solde_compte -= montant
            total_credit += montant
        lignes_bancaires.append({"transaction": t, "solde": solde_compte})

    # Suivi des fournisseurs du mois (factures, hors acompte de démarrage)
    factures_fournisseurs_rows = (
        db.session.query(Fournisseur, func.sum(FactureFournisseur.montant_net_paye))
        .join(FactureFournisseur, FactureFournisseur.fournisseur_id == Fournisseur.id)
        .filter(extract("year", FactureFournisseur.date_facture) == annee, extract("month", FactureFournisseur.date_facture) == mois)
        .group_by(Fournisseur.id)
        .order_by(func.sum(FactureFournisseur.montant_net_paye).desc())
        .all()
    )
    total_fournisseurs_mois = sum(float(m) for _, m in factures_fournisseurs_rows)
    suivi_fournisseurs = [
        {
            "label": fournisseur.nom_societe,
            "montant": float(montant),
            "taux_acompte": fournisseur.taux_acompte,
            "pourcentage": round(float(montant) / total_fournisseurs_mois * 100, 1) if total_fournisseurs_mois else 0,
        }
        for fournisseur, montant in factures_fournisseurs_rows
    ]

    bulletins_mois = (
        Salaire.query.filter_by(mois=mois, annee=annee)
        .join(Employe)
        .order_by(Employe.nom)
        .all()
    )
    masse_salariale = sum(float(b.montant) for b in bulletins_mois)
    nb_bulletins_payes = sum(1 for b in bulletins_mois if b.statut == "paye")
    nb_bulletins_attente = len(bulletins_mois) - nb_bulletins_payes

    nb_fournisseurs_actifs = Fournisseur.query.filter_by(actif=True).count()

    consommables_mois = (
        SuiviConsommable.query.filter_by(mois=mois, annee=annee)
        .join(Consommable)
        .order_by(Consommable.nom)
        .all()
    )
    total_consommables = sum(float(c.montant) for c in consommables_mois)
    nb_consommables_payes = sum(1 for c in consommables_mois if c.paye)

    # Évolution vs mois précédent
    mois_prec, annee_prec = _mois_precedent(mois, annee)
    totaux_prec = _totaux_mois(mois_prec, annee_prec)

    evolution = {
        "depenses": {
            "actuel": total_depenses, "precedent": totaux_prec["depenses"],
            **_variation(total_depenses, totaux_prec["depenses"]),
        },
        "masse_salariale": {
            "actuel": masse_salariale, "precedent": totaux_prec["masse_salariale"],
            **_variation(masse_salariale, totaux_prec["masse_salariale"]),
        },
        "consommables": {
            "actuel": total_consommables, "precedent": totaux_prec["consommables"],
            **_variation(total_consommables, totaux_prec["consommables"]),
        },
        "solde_compte": {
            "actuel": solde_compte, "precedent": totaux_prec["solde_compte"],
            **_variation(solde_compte, totaux_prec["solde_compte"]),
        },
        "mois_precedent_label": f"{MOIS_FR[mois_prec - 1]} {annee_prec}",
    }

    # Transactions détaillées du mois
    depenses_mois = Depense.query.filter(*filtre_depenses).order_by(Depense.date.desc(), Depense.id.desc()).all()

    # Résumé de présence (agrégé sur les employés actifs)
    employes_actifs = Employe.query.filter_by(actif=True).all()
    total_jours_travailles = 0
    total_jours_absence = 0
    for employe in employes_actifs:
        jt, ja = calculer_presence_mensuelle(employe.id, mois, annee)
        total_jours_travailles += jt or 0
        total_jours_absence += ja or 0

    total_jours_presence = total_jours_travailles + total_jours_absence
    taux_presence_global = (
        round(total_jours_travailles / total_jours_presence * 100, 1) if total_jours_presence else None
    )

    return render_template(
        "rapports/index.html",
        mois=mois,
        annee=annee,
        mois_fr=MOIS_FR,
        annees=range(today.year - 2, today.year + 2),
        statuts_salaire=STATUTS_SALAIRE,
        kpis={
            "total_depenses": total_depenses,
            "nb_depenses": nb_depenses,
            "masse_salariale": masse_salariale,
            "nb_bulletins_payes": nb_bulletins_payes,
            "nb_bulletins_attente": nb_bulletins_attente,
            "nb_fournisseurs_actifs": nb_fournisseurs_actifs,
            "total_consommables": total_consommables,
            "nb_consommables": len(consommables_mois),
            "nb_consommables_payes": nb_consommables_payes,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "solde_compte": solde_compte,
        },
        depenses_par_categorie=depenses_par_categorie,
        suivi_fournisseurs=suivi_fournisseurs,
        bulletins_mois=bulletins_mois,
        consommables_mois=consommables_mois,
        evolution=evolution,
        depenses_mois=depenses_mois,
        lignes_bancaires=lignes_bancaires,
        solde_ouverture=solde_ouverture,
        presence={
            "jours_travailles": total_jours_travailles,
            "jours_absence": total_jours_absence,
            "taux": taux_presence_global,
            "nb_employes": len(employes_actifs),
        },
        now=datetime.now(),
    )
