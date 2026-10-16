from datetime import date, datetime

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
            date_facture_initiale=_parse_date(request.form.get("date_facture_initiale")),
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
        erreurs = _valider_formulaire(request.form, fournisseur=fournisseur)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("fournisseurs/form.html", fournisseur=fournisseur, form=request.form)

        fournisseur.nom_societe = request.form.get("nom_societe", "").strip()
        fournisseur.numero_marche = request.form.get("numero_marche", "").strip() or None
        fournisseur.date_signature = _parse_date(request.form.get("date_signature"))
        fournisseur.montant_marche = _parse_decimal(request.form.get("montant_marche"))
        fournisseur.montant_acompte_initial = _parse_decimal(request.form.get("montant_acompte_initial"))
        fournisseur.date_facture_initiale = _parse_date(request.form.get("date_facture_initiale"))
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
        "date_facture_initiale": fournisseur.date_facture_initiale.isoformat() if fournisseur.date_facture_initiale else "",
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
            "date_facture": fournisseur.date_facture_initiale,
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


def _ajouter_un_an(valeur):
    try:
        return valeur.replace(year=valeur.year + 1)
    except ValueError:
        # 29 février : on retombe sur le 1er mars de l'année suivante.
        return valeur.replace(month=3, day=1, year=valeur.year + 1)


def _garantie_bonne_execution(fournisseur, lignes):
    """Garantie de bonne exécution : 5% du montant du marché, retenus et livrés au
    fournisseur un an après qu'il a touché 95% du montant total du marché."""
    montant_marche = float(fournisseur.montant_marche) if fournisseur.montant_marche else 0.0
    if montant_marche <= 0:
        return None

    montant_garantie = round(montant_marche * 0.05, 2)
    seuil_95 = montant_marche * 0.95

    cumul = 0.0
    date_seuil_atteint = None
    for ligne in lignes:
        cumul += ligne["montant_net"]
        date_mouvement = ligne["date_paiement"] or ligne["date_facture"]
        if date_seuil_atteint is None and cumul >= seuil_95 and date_mouvement:
            date_seuil_atteint = date_mouvement

    date_liberation = _ajouter_un_an(date_seuil_atteint) if date_seuil_atteint else None
    livree_le = fournisseur.garantie_livree_le

    if livree_le:
        statut = "livree"
    elif date_liberation and date.today() >= date_liberation:
        statut = "disponible"
    elif date_liberation:
        statut = "en_attente_date"
    else:
        statut = "en_attente_seuil"

    return {
        "montant": montant_garantie,
        "montant_restant_avant_seuil": max(seuil_95 - cumul, 0) if date_seuil_atteint is None else 0,
        "date_seuil_atteint": date_seuil_atteint,
        "date_liberation": date_liberation,
        "livree_le": livree_le,
        "statut": statut,
    }


@fournisseurs_bp.route("/<int:fournisseur_id>/mouvement")
@role_required("fournisseurs")
def mouvement(fournisseur_id):
    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)
    lignes = _calculer_mouvement(fournisseur)
    garantie = _garantie_bonne_execution(fournisseur, lignes)

    montant_restant_a_payer = None
    if fournisseur.montant_marche:
        montant_paye = fournisseur.montant_acompte or 0.0
        montant_restant_a_payer = max((float(fournisseur.montant_marche) * 0.95) - montant_paye, 0)

    return render_template(
        "fournisseurs/mouvement.html", fournisseur=fournisseur, lignes=lignes, garantie=garantie,
        montant_restant_a_payer=montant_restant_a_payer,
        now=datetime.now(), today=date.today().isoformat(),
    )


@fournisseurs_bp.route("/<int:fournisseur_id>/factures/nouvelle", methods=["POST"])
@role_required("fournisseurs")
def nouvelle_facture(fournisseur_id):
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de facture.", "warning")
        return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))

    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)
    date_facture = _parse_date(request.form.get("date_facture"))
    montant_net_paye = _parse_decimal(request.form.get("montant_net_paye"))
    erreur_plafond = _verifier_plafond_marche(fournisseur, montant_net_paye) if montant_net_paye else None

    if not date_facture:
        flash("La date de la facture est invalide ou manquante.", "danger")
    elif montant_net_paye is None or montant_net_paye <= 0:
        flash("Le montant net payé de la facture est invalide.", "danger")
    elif erreur_plafond:
        flash(erreur_plafond, "danger")
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
    erreur_plafond = (
        _verifier_plafond_marche(facture.fournisseur, montant_net_paye, facture_id_exclue=facture.id)
        if montant_net_paye else None
    )

    if not date_facture:
        flash("La date de la facture est invalide ou manquante.", "danger")
    elif montant_net_paye is None or montant_net_paye <= 0:
        flash("Le montant net payé de la facture est invalide.", "danger")
    elif erreur_plafond:
        flash(erreur_plafond, "danger")
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


@fournisseurs_bp.route("/<int:fournisseur_id>/factures/<int:facture_id>/devalider", methods=["POST"])
@admin_required
def devalider_facture(fournisseur_id, facture_id):
    facture = db.get_or_404(FactureFournisseur, facture_id)

    if not facture.valide:
        flash("Cette facture n'est pas validée.", "info")
    else:
        facture.valide = False
        facture.valide_le = None
        db.session.commit()
        flash("Facture déverrouillée, elle peut de nouveau être modifiée.", "success")

    return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))


@fournisseurs_bp.route("/<int:fournisseur_id>/garantie/livrer", methods=["POST"])
@admin_required
def garantie_livrer(fournisseur_id):
    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)

    if fournisseur.garantie_livree_le:
        flash("La garantie de bonne exécution est déjà marquée comme livrée.", "info")
        return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))

    date_livraison = _parse_date(request.form.get("date_livraison")) or date.today()
    fournisseur.garantie_livree_le = date_livraison
    db.session.commit()
    flash("Garantie de bonne exécution marquée comme livrée.", "success")
    return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))


@fournisseurs_bp.route("/<int:fournisseur_id>/garantie/annuler", methods=["POST"])
@admin_required
def garantie_annuler(fournisseur_id):
    fournisseur = db.get_or_404(Fournisseur, fournisseur_id)

    if not fournisseur.garantie_livree_le:
        flash("La garantie de bonne exécution n'est pas marquée comme livrée.", "info")
    else:
        fournisseur.garantie_livree_le = None
        db.session.commit()
        flash("Livraison de la garantie annulée.", "success")

    return redirect(url_for("fournisseurs.mouvement", fournisseur_id=fournisseur_id))


def _verifier_plafond_marche(fournisseur, montant_facture, facture_id_exclue=None):
    """Empêche le cumul (acompte + factures) de dépasser 95% du montant du marché :
    les 5% restants sont la garantie de bonne exécution, livrée séparément."""
    if not fournisseur.montant_marche:
        return None

    montant_marche = float(fournisseur.montant_marche)
    seuil_95 = montant_marche * 0.95
    acompte_initial = float(fournisseur.montant_acompte_initial) if fournisseur.montant_acompte_initial else 0.0
    total_autres_factures = sum(
        float(f.montant_net_paye) for f in fournisseur.factures if f.id != facture_id_exclue
    )
    cumul_apres = acompte_initial + total_autres_factures + montant_facture

    if cumul_apres > seuil_95:
        return (
            f"Montant refusé : le cumul payé atteindrait {cumul_apres:,.0f} KMF, "
            f"ce qui dépasse 95% du montant du marché ({seuil_95:,.0f} KMF). "
            f"Les 5% restants sont la garantie de bonne exécution, à valider depuis cette section."
        ).replace(",", " ")
    return None


def _valider_formulaire(form, fournisseur=None):
    erreurs = []
    if not form.get("nom_societe", "").strip():
        erreurs.append("Le nom de la société est obligatoire.")

    for champ, label in [("montant_marche", "Le montant du marché"), ("montant_acompte_initial", "Le montant de l'acompte")]:
        valeur_brute = form.get(champ, "").strip()
        if valeur_brute and _parse_decimal(valeur_brute) is None:
            erreurs.append(f"{label} est invalide.")

    montant_marche = _parse_decimal(form.get("montant_marche"))
    montant_acompte_initial = _parse_decimal(form.get("montant_acompte_initial"))
    if montant_acompte_initial is not None and montant_marche is None:
        erreurs.append("Le montant du marché est requis pour saisir un montant d'acompte.")
    elif montant_acompte_initial is not None and montant_marche is not None:
        seuil_95 = montant_marche * 0.95
        total_factures = sum(float(f.montant_net_paye) for f in fournisseur.factures) if fournisseur else 0.0
        if montant_acompte_initial + total_factures > seuil_95:
            if total_factures:
                erreurs.append(
                    (
                        f"Le montant de l'acompte, cumulé aux factures déjà enregistrées "
                        f"({total_factures:,.0f} KMF), ne peut pas dépasser 95% du montant du marché "
                        f"({seuil_95:,.0f} KMF) — les 5% restants sont la garantie de bonne exécution."
                    ).replace(",", " ")
                )
            else:
                erreurs.append(
                    (
                        f"Le montant de l'acompte ne peut pas dépasser 95% du montant du marché "
                        f"({seuil_95:,.0f} KMF) — les 5% restants sont la garantie de bonne exécution."
                    ).replace(",", " ")
                )

    return erreurs
