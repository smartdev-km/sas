from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.decorators import role_required, admin_required

from app import db
from app.models import Fournisseur, FactureFournisseur

fournisseurs_bp = Blueprint("fournisseurs", __name__, url_prefix="/fournisseurs")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@fournisseurs_bp.route("/")
@role_required("fournisseurs")
def liste():
    fournisseurs = Fournisseur.query.order_by(Fournisseur.actif.desc(), Fournisseur.nom_societe).all()
    return render_template("fournisseurs/liste.html", fournisseurs=fournisseurs)


@fournisseurs_bp.route("/nouveau", methods=["GET", "POST"])
@role_required("fournisseurs")
def nouveau():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de fournisseur directement.", "warning")
        return redirect(url_for("fournisseurs.liste"))

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("fournisseurs/form.html", fournisseur=None, form=request.form)

        fournisseur = Fournisseur(
            nom_societe=request.form.get("nom_societe", "").strip(),
            numero_marche=request.form.get("numero_marche", "").strip() or None,
            date_signature=_parse_date(request.form.get("date_signature")),
            montant_marche=_parse_decimal(request.form.get("montant_marche")),
            montant_acompte_initial=_parse_decimal(request.form.get("montant_acompte_initial")),
            date_versement_initial=_parse_date(request.form.get("date_versement_initial")),
            actif=True,
        )
        db.session.add(fournisseur)
        db.session.commit()
        flash("Fournisseur ajouté avec succès.", "success")
        return redirect(url_for("fournisseurs.liste"))

    return render_template("fournisseurs/form.html", fournisseur=None, form={})


@fournisseurs_bp.route("/<int:fournisseur_id>/modifier", methods=["GET", "POST"])
@role_required("fournisseurs")
def modifier(fournisseur_id):
    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("fournisseurs/form.html", fournisseur=fournisseur, form=request.form)

        fournisseur.nom_societe = request.form.get("nom_societe", "").strip()
        fournisseur.numero_marche = request.form.get("numero_marche", "").strip() or None
        fournisseur.date_signature = _parse_date(request.form.get("date_signature"))
        fournisseur.montant_marche = _parse_decimal(request.form.get("montant_marche"))
        fournisseur.montant_acompte_initial = _parse_decimal(request.form.get("montant_acompte_initial"))
        fournisseur.date_versement_initial = _parse_date(request.form.get("date_versement_initial"))
        db.session.commit()
        flash("Fournisseur modifié avec succès.", "success")
        return redirect(url_for("fournisseurs.liste"))

    form = {
        "nom_societe": fournisseur.nom_societe,
        "numero_marche": fournisseur.numero_marche or "",
        "date_signature": fournisseur.date_signature.isoformat() if fournisseur.date_signature else "",
        "montant_marche": fournisseur.montant_marche,
        "montant_acompte_initial": fournisseur.montant_acompte_initial,
        "date_versement_initial": fournisseur.date_versement_initial.isoformat() if fournisseur.date_versement_initial else "",
    }
    return render_template("fournisseurs/form.html", fournisseur=fournisseur, form=form)


@fournisseurs_bp.route("/<int:fournisseur_id>/toggle-actif", methods=["POST"])
@role_required("fournisseurs")
def toggle_actif(fournisseur_id):
    if current_user.role == "comptable":
        flash("Un compte RAF ne peut pas activer/désactiver un fournisseur.", "warning")
        return redirect(url_for("fournisseurs.liste"))

    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)
    fournisseur.actif = not fournisseur.actif
    db.session.commit()
    flash(f"Fournisseur {'réactivé' if fournisseur.actif else 'désactivé'}.", "info")
    return redirect(url_for("fournisseurs.liste"))


@fournisseurs_bp.route("/<int:fournisseur_id>/supprimer", methods=["POST"])
@role_required("fournisseurs")
def supprimer(fournisseur_id):
    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)
    db.session.delete(fournisseur)
    db.session.commit()
    flash("Fournisseur supprimé.", "info")
    return redirect(url_for("fournisseurs.liste"))


def _calculer_mouvement(fournisseur):
    """Calcule le tableau de suivi (solde du marché, taux d'exécution) à partir des factures du fournisseur.

    La ligne N°0 représente l'acompte de démarrage lui-même (dérivée de montant_acompte_initial /
    date_versement_initial du fournisseur, pas stockée comme facture), et alimente le cumul dès
    le départ, comme dans une fiche de suivi d'engagement classique. Chaque montant net payé
    (acompte compris) vient directement réduire le solde du marché restant à payer.
    """
    factures = FactureFournisseur.query.filter_by(fournisseur_id=fournisseur.id).order_by(
        FactureFournisseur.date_facture, FactureFournisseur.id
    ).all()

    montant_marche = float(fournisseur.montant_marche) if fournisseur.montant_marche else 0.0
    montant_acompte_initial = float(fournisseur.montant_acompte_initial) if fournisseur.montant_acompte_initial else 0.0

    lignes = []
    cumul_paye = 0.0
    compteur = 0

    if montant_acompte_initial > 0:
        cumul_paye += montant_acompte_initial
        lignes.append({
            "numero": compteur,
            "facture": None,
            "reference": "Acompte de démarrage",
            "date_facture": None,
            "date_paiement": fournisseur.date_versement_initial,
            "montant_net": montant_acompte_initial,
            "solde_marche_restant": montant_marche - cumul_paye,
            "taux_execution": round(cumul_paye / montant_marche * 100, 1) if montant_marche else None,
            "est_acompte": True,
        })

    for facture in factures:
        compteur += 1
        montant_net = float(facture.montant_net_paye)
        cumul_paye += montant_net

        lignes.append({
            "numero": compteur,
            "facture": facture,
            "reference": facture.reference,
            "date_facture": facture.date_facture,
            "date_paiement": facture.date_paiement,
            "montant_net": montant_net,
            "solde_marche_restant": montant_marche - cumul_paye,
            "taux_execution": round(cumul_paye / montant_marche * 100, 1) if montant_marche else None,
            "est_acompte": False,
        })

    return lignes


@fournisseurs_bp.route("/<int:fournisseur_id>/mouvement")
@role_required("fournisseurs")
def mouvement(fournisseur_id):
    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)
    lignes = _calculer_mouvement(fournisseur)
    return render_template(
        "fournisseurs/mouvement.html", fournisseur=fournisseur, lignes=lignes, now=datetime.now(),
    )


@fournisseurs_bp.route("/<int:fournisseur_id>/factures/nouvelle", methods=["POST"])
@role_required("fournisseurs")
def nouvelle_facture(fournisseur_id):
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de facture.", "warning")
        return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))

    db.get_or_404(Fournisseur, fournisseur_id)
    date_facture = _parse_date(request.form.get("date_facture"))
    montant_net_paye = _parse_decimal(request.form.get("montant_net_paye"))

    if not date_facture:
        flash("La date de la facture est invalide ou manquante.", "danger")
    elif montant_net_paye is None or montant_net_paye <= 0:
        flash("Le montant net payé de la facture est invalide.", "danger")
    else:
        db.session.add(FactureFournisseur(
            fournisseur_id=fournisseur_id,
            reference=request.form.get("reference", "").strip() or None,
            date_facture=date_facture,
            date_paiement=_parse_date(request.form.get("date_paiement")),
            montant_net_paye=montant_net_paye,
        ))
        db.session.commit()
        flash("Facture ajoutée.", "success")

    return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))


@fournisseurs_bp.route("/<int:fournisseur_id>/factures/<int:facture_id>/modifier", methods=["POST"])
@role_required("fournisseurs")
def modifier_facture(fournisseur_id, facture_id):
    facture = db.get_or_404(FactureFournisseur, facture_id)

    if facture.valide:
        flash("Cette facture est validée, elle ne peut plus être modifiée.", "danger")
        return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))

    date_facture = _parse_date(request.form.get("date_facture"))
    montant_net_paye = _parse_decimal(request.form.get("montant_net_paye"))

    if not date_facture:
        flash("La date de la facture est invalide ou manquante.", "danger")
    elif montant_net_paye is None or montant_net_paye <= 0:
        flash("Le montant net payé de la facture est invalide.", "danger")
    else:
        facture.reference = request.form.get("reference", "").strip() or None
        facture.date_facture = date_facture
        facture.date_paiement = _parse_date(request.form.get("date_paiement"))
        facture.montant_net_paye = montant_net_paye
        db.session.commit()
        flash("Facture modifiée.", "success")

    return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))


@fournisseurs_bp.route("/<int:fournisseur_id>/factures/<int:facture_id>/supprimer", methods=["POST"])
@role_required("fournisseurs")
def supprimer_facture(fournisseur_id, facture_id):
    facture = db.get_or_404(FactureFournisseur, facture_id)

    if facture.valide:
        flash("Cette facture est validée, elle ne peut plus être supprimée.", "danger")
        return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))

    db.session.delete(facture)
    db.session.commit()
    flash("Facture supprimée.", "info")
    return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))


@fournisseurs_bp.route("/<int:fournisseur_id>/factures/<int:facture_id>/valider", methods=["POST"])
@admin_required
def valider_facture(fournisseur_id, facture_id):
    facture = db.get_or_404(FactureFournisseur, facture_id)

    if facture.valide:
        flash("Cette facture est déjà validée.", "info")
    else:
        facture.valide = True
        facture.valide_le = datetime.now()
        db.session.commit()
        flash("Facture validée. Elle ne peut plus être modifiée ni supprimée.", "success")

    return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))


def _valider_formulaire(form):
    erreurs = []
    if not form.get("nom_societe", "").strip():
        erreurs.append("Le nom de la société est obligatoire.")

    for champ, label in [("montant_marche", "Le montant du marché"), ("montant_acompte_initial", "Le montant de l'acompte")]:
        valeur_brute = form.get(champ, "").strip()
        if valeur_brute and _parse_decimal(valeur_brute) is None:
            erreurs.append(f"{label} est invalide.")

    montant_marche = _parse_decimal(form.get("montant_marche"))
    montant_acompte_initial = _parse_decimal(form.get("montant_acompte_initial"))
    if montant_acompte_initial is not None and montant_marche is not None and montant_acompte_initial > montant_marche:
        erreurs.append("Le montant de l'acompte ne peut pas dépasser le montant du marché.")
    if montant_acompte_initial is not None and montant_marche is None:
        erreurs.append("Le montant du marché est requis pour saisir un montant d'acompte.")

    return erreurs
