from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import func
from app.decorators import role_required, admin_required

from app import db
from app.models import Consommable, SuiviConsommable, Depense
from app.constants import MOIS_FR

consommables_bp = Blueprint("consommables", __name__, url_prefix="/consommables")

TYPES_PAR_DEFAUT = ["Internet", "Data mobile", "Encre", "Papier A4", "Eau", "Électricité"]


def _budget():
    """Budget Consommables : dépenses validées de catégorie « Consommables »,
    moins tout ce qui a déjà été réparti dans le suivi des consommables."""
    alloue = float(
        db.session.query(func.sum(Depense.montant))
        .filter(Depense.categorie == "Consommables", Depense.valide.is_(True))
        .scalar() or 0
    )
    depense = float(
        db.session.query(func.sum(SuiviConsommable.montant)).scalar() or 0
    )
    return alloue, depense, alloue - depense


def _assurer_types_par_defaut():
    if Consommable.query.first():
        return
    for nom in TYPES_PAR_DEFAUT:
        db.session.add(Consommable(nom=nom, actif=True))
    db.session.commit()


def _assurer_suivis_du_mois(mois, annee):
    _assurer_types_par_defaut()
    types_actifs = Consommable.query.filter_by(actif=True).all()
    existants = {
        s.consommable_id
        for s in SuiviConsommable.query.filter_by(mois=mois, annee=annee).all()
    }
    cree = False
    for consommable in types_actifs:
        if consommable.id not in existants:
            db.session.add(SuiviConsommable(consommable_id=consommable.id, mois=mois, annee=annee, montant=0))
            cree = True
    if cree:
        db.session.commit()


@consommables_bp.route("/")
@role_required("consommables")
def liste():
    today = date.today()
    annee = request.args.get("annee", today.year, type=int)
    mois = request.args.get("mois", today.month, type=int)

    _assurer_suivis_du_mois(mois, annee)

    suivis = (
        SuiviConsommable.query.filter_by(mois=mois, annee=annee)
        .join(Consommable)
        .order_by(Consommable.nom)
        .all()
    )

    total = sum(float(s.montant) for s in suivis)
    nb_payes = sum(1 for s in suivis if s.paye)
    budget_alloue, budget_depense, budget_restant = _budget()

    return render_template(
        "consommables/liste.html",
        suivis=suivis,
        mois=mois,
        annee=annee,
        mois_fr=MOIS_FR,
        annees=range(today.year - 2, today.year + 2),
        total=total,
        nb_payes=nb_payes,
        budget_alloue=budget_alloue,
        budget_depense=budget_depense,
        budget_restant=budget_restant,
    )


@consommables_bp.route("/<int:suivi_id>/modifier", methods=["POST"])
@role_required("consommables")
def modifier(suivi_id):
    suivi = db.get_or_404(SuiviConsommable, suivi_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas modifier un consommable, seulement le valider.", "warning")
        return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))

    if suivi.valide:
        flash(f"{suivi.consommable.nom} est validé, il ne peut plus être modifié.", "warning")
        return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))

    montant_brut = request.form.get("montant", "0").strip() or "0"
    try:
        montant = float(montant_brut)
        if montant < 0:
            raise ValueError
    except ValueError:
        flash("Montant invalide.", "danger")
        return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))

    _, budget_depense, budget_restant = _budget()
    disponible_pour_ce_suivi = budget_restant + float(suivi.montant)
    if montant > disponible_pour_ce_suivi:
        flash(
            f"Montant refusé : il dépasse le budget Consommables disponible "
            f"({disponible_pour_ce_suivi:.0f} KMF restants).",
            "danger",
        )
        return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))

    suivi.montant = montant
    suivi.notes = request.form.get("notes", "").strip() or None

    db.session.commit()
    flash(f"{suivi.consommable.nom} mis à jour.", "success")
    return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))


@consommables_bp.route("/<int:suivi_id>/toggle-paye", methods=["POST"])
@role_required("consommables")
def toggle_paye(suivi_id):
    suivi = db.get_or_404(SuiviConsommable, suivi_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas modifier un consommable, seulement le valider.", "warning")
        return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))

    if suivi.valide:
        flash(f"{suivi.consommable.nom} est validé, il ne peut plus être modifié.", "warning")
        return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))

    suivi.paye = not suivi.paye
    suivi.date_paiement = date.today() if suivi.paye else None
    db.session.commit()
    flash(f"{suivi.consommable.nom} marqué comme {'payé' if suivi.paye else 'non payé'}.", "success")
    return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))


@consommables_bp.route("/<int:suivi_id>/valider", methods=["POST"])
@admin_required
def valider(suivi_id):
    suivi = db.get_or_404(SuiviConsommable, suivi_id)

    if suivi.valide:
        flash(f"{suivi.consommable.nom} est déjà validé.", "info")
    else:
        suivi.valide = True
        suivi.valide_le = datetime.now()
        db.session.commit()
        flash(f"{suivi.consommable.nom} validé. Il ne peut plus être modifié.", "success")

    return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))


@consommables_bp.route("/<int:suivi_id>/devalider", methods=["POST"])
@admin_required
def devalider(suivi_id):
    suivi = db.get_or_404(SuiviConsommable, suivi_id)

    if not suivi.valide:
        flash(f"{suivi.consommable.nom} n'est pas validé.", "info")
    else:
        suivi.valide = False
        suivi.valide_le = None
        db.session.commit()
        flash(f"{suivi.consommable.nom} déverrouillé, il peut de nouveau être modifié.", "success")

    return redirect(url_for("consommables.liste", mois=suivi.mois, annee=suivi.annee))


@consommables_bp.route("/types/nouveau", methods=["POST"])
@role_required("consommables")
def type_nouveau():
    nom = request.form.get("nom", "").strip()
    mois = request.form.get("mois", type=int)
    annee = request.form.get("annee", type=int)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de consommable directement.", "warning")
        return redirect(url_for("consommables.liste", mois=mois, annee=annee))

    if not nom:
        flash("Le nom est obligatoire.", "danger")
    elif Consommable.query.filter(Consommable.nom.ilike(nom)).first():
        flash(f"« {nom} » existe déjà.", "danger")
    else:
        db.session.add(Consommable(nom=nom, actif=True))
        db.session.commit()
        flash(f"« {nom} » ajouté.", "success")

    return redirect(url_for("consommables.liste", mois=mois, annee=annee))


@consommables_bp.route("/types/<int:consommable_id>/toggle-actif", methods=["POST"])
@role_required("consommables")
def type_toggle_actif(consommable_id):
    consommable = db.get_or_404(Consommable, consommable_id)
    consommable.actif = not consommable.actif
    db.session.commit()
    flash(f"« {consommable.nom} » {'réactivé' if consommable.actif else 'désactivé'}.", "info")
    return redirect(url_for("consommables.liste"))
