from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user

from app import db
from app.models import ClientCommercial, Villa, VillaAttribution
from app.decorators import role_required
from app.constants import (
    TYPES_CLIENT, STATUTS_CLIENT, STATUTS_CLIENT_COULEUR,
    PROJETS_ACQUISITION, MODES_FINANCEMENT, INTENTIONS_ACHAT,
    STATUTS_VILLA, STATUTS_VILLA_COULEUR, STATUTS_ATTRIBUTION_VILLA,
)

commercial_bp = Blueprint("commercial", __name__, url_prefix="/commercial")

STATUTS_AVEC_RELANCE = {"rdv_cale", "prochaine_relance"}


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


def _valider_formulaire(form):
    erreurs = []

    if not form.get("nom_client", "").strip():
        erreurs.append("Le nom du client est obligatoire.")

    if not _parse_date(form.get("date_contact")):
        erreurs.append("La date de contact est invalide ou manquante.")

    type_client = form.get("type_client")
    if type_client not in TYPES_CLIENT:
        erreurs.append("Le type de client est invalide.")
    elif type_client == "autre" and not form.get("type_client_precision", "").strip():
        erreurs.append("Merci de préciser le type de client.")

    if form.get("statut") not in STATUTS_CLIENT:
        erreurs.append("Le statut est invalide.")

    budget_brut = form.get("budget", "").strip()
    if budget_brut and _parse_decimal(budget_brut) is None:
        erreurs.append("Le budget est invalide.")

    for champ, libelle in (("budget_min", "Budget minimum"), ("budget_max", "Budget maximum")):
        brut = form.get(champ, "").strip()
        if brut and _parse_decimal(brut) is None:
            erreurs.append(f"{libelle} est invalide.")

    nombre_villas_brut = form.get("nombre_villas_envisage", "").strip()
    if nombre_villas_brut:
        try:
            if int(nombre_villas_brut) < 0:
                raise ValueError
        except ValueError:
            erreurs.append("Le nombre de villas envisagé est invalide.")

    projet = form.get("projet_acquisition", "")
    if projet and projet not in PROJETS_ACQUISITION:
        erreurs.append("Le projet d'acquisition est invalide.")
    elif projet == "autre" and not form.get("projet_acquisition_autre", "").strip():
        erreurs.append("Merci de préciser le projet d'acquisition.")

    intention = form.get("intention_achat", "")
    if intention and intention not in INTENTIONS_ACHAT:
        erreurs.append("L'intention d'achat est invalide.")

    return erreurs


def _mode_financement_depuis_form(form):
    choix = form.getlist("mode_financement")
    return ",".join(m for m in choix if m in MODES_FINANCEMENT) or None


def _contexte_formulaire(**extra):
    return dict(
        types_client=TYPES_CLIENT, statuts_client=STATUTS_CLIENT,
        projets_acquisition=PROJETS_ACQUISITION, modes_financement=MODES_FINANCEMENT,
        intentions_achat=INTENTIONS_ACHAT,
        toutes_les_villas=Villa.query.order_by(Villa.numero).all(),
        statuts_villa=STATUTS_VILLA, statuts_attribution_villa=STATUTS_ATTRIBUTION_VILLA,
        **extra,
    )


def _appliquer_formulaire(client, form):
    type_client = form.get("type_client")
    statut = form.get("statut")
    projet = form.get("projet_acquisition", "") or None

    client.date_contact = _parse_date(form.get("date_contact"))
    client.numero_piece_identite = form.get("numero_piece_identite", "").strip() or None
    client.type_client = type_client
    client.type_client_precision = form.get("type_client_precision", "").strip() or None if type_client == "autre" else None
    client.statut = statut
    client.nom_client = form.get("nom_client", "").strip()
    client.profession = form.get("profession", "").strip() or None
    client.societe = form.get("societe", "").strip() or None
    client.telephone = form.get("telephone", "").strip() or None
    client.whatsapp = form.get("whatsapp", "").strip() or None
    client.email = form.get("email", "").strip() or None
    client.lieu_residence = form.get("lieu_residence", "").strip() or None
    nombre_villas_brut = form.get("nombre_villas_envisage", "").strip()
    client.nombre_villas_envisage = int(nombre_villas_brut) if nombre_villas_brut else None

    client.projet_acquisition = projet
    client.projet_acquisition_autre = form.get("projet_acquisition_autre", "").strip() or None if projet == "autre" else None

    client.budget = _parse_decimal(form.get("budget")) if type_client == "investisseur" else None
    client.budget_min = _parse_decimal(form.get("budget_min"))
    client.budget_max = _parse_decimal(form.get("budget_max"))
    client.mode_financement = _mode_financement_depuis_form(form)

    client.intention_achat = form.get("intention_achat", "") or None

    client.villa_interessee = form.get("villa_interessee", "").strip() or None
    client.prochaine_relance = _parse_date(form.get("prochaine_relance")) if statut in STATUTS_AVEC_RELANCE else None
    client.notes = form.get("notes", "").strip() or None


@commercial_bp.route("/")
@role_required("commercial")
def liste():
    statut_filtre = request.args.get("statut", "")

    query = ClientCommercial.query
    if statut_filtre in STATUTS_CLIENT:
        query = query.filter_by(statut=statut_filtre)

    clients = query.order_by(ClientCommercial.date_contact.desc(), ClientCommercial.id.desc()).all()

    return render_template(
        "commercial/liste.html",
        clients=clients,
        types_client=TYPES_CLIENT,
        statuts_client=STATUTS_CLIENT,
        statuts_couleur=STATUTS_CLIENT_COULEUR,
        statut_filtre=statut_filtre,
    )


@commercial_bp.route("/nouveau", methods=["GET", "POST"])
@role_required("commercial")
def nouveau():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de client directement.", "warning")
        return redirect(url_for("commercial.liste"))

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "commercial/form.html", client=None, form=request.form,
                **_contexte_formulaire(),
            )

        client = ClientCommercial(cree_par_id=current_user.id)
        _appliquer_formulaire(client, request.form)
        db.session.add(client)
        db.session.commit()
        flash("Client ajouté avec succès.", "success")
        return redirect(url_for("commercial.liste"))

    return render_template(
        "commercial/form.html", client=None, form={},
        **_contexte_formulaire(),
    )


@commercial_bp.route("/<int:client_id>/modifier", methods=["GET", "POST"])
@role_required("commercial")
def modifier(client_id):
    client = db.get_or_404(ClientCommercial, client_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas modifier une fiche client.", "warning")
        return redirect(url_for("commercial.liste"))

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "commercial/form.html", client=client, form=request.form,
                **_contexte_formulaire(),
            )

        _appliquer_formulaire(client, request.form)
        db.session.commit()
        flash("Client modifié avec succès.", "success")
        return redirect(url_for("commercial.liste"))

    form = {
        "date_contact": client.date_contact.isoformat() if client.date_contact else "",
        "numero_piece_identite": client.numero_piece_identite or "",
        "nom_client": client.nom_client,
        "profession": client.profession or "",
        "societe": client.societe or "",
        "telephone": client.telephone or "",
        "whatsapp": client.whatsapp or "",
        "email": client.email or "",
        "lieu_residence": client.lieu_residence or "",
        "nombre_villas_envisage": client.nombre_villas_envisage,
        "type_client": client.type_client,
        "type_client_precision": client.type_client_precision or "",
        "projet_acquisition": client.projet_acquisition or "",
        "projet_acquisition_autre": client.projet_acquisition_autre or "",
        "budget": client.budget,
        "budget_min": client.budget_min,
        "budget_max": client.budget_max,
        "mode_financement": client.mode_financement_liste(),
        "intention_achat": client.intention_achat or "",
        "villa_interessee": client.villa_interessee or "",
        "statut": client.statut,
        "prochaine_relance": client.prochaine_relance.isoformat() if client.prochaine_relance else "",
        "notes": client.notes or "",
    }
    return render_template(
        "commercial/form.html", client=client, form=form,
        **_contexte_formulaire(),
    )


@commercial_bp.route("/<int:client_id>/supprimer", methods=["POST"])
@role_required("commercial")
def supprimer(client_id):
    client = db.get_or_404(ClientCommercial, client_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas supprimer une fiche client.", "warning")
        return redirect(url_for("commercial.liste"))

    villas_concernees = [a.villa for a in client.villa_attributions]
    for attribution in list(client.villa_attributions):
        db.session.delete(attribution)
    db.session.delete(client)
    for villa in villas_concernees:
        _recalculer_statut_villa(villa)
    db.session.commit()
    flash("Client supprimé.", "info")
    return redirect(url_for("commercial.liste"))


# --- Villas ----------------------------------------------------------------

def _recalculer_statut_villa(villa):
    """Le statut d'une villa dérive de ses attributions : vendue > réservée > disponible."""
    attributions = villa.attributions
    if any(a.statut == "vendue" for a in attributions):
        villa.statut = "vendue"
    elif any(a.statut == "reservee" for a in attributions):
        villa.statut = "reservee"
    else:
        villa.statut = "disponible"


@commercial_bp.route("/villas")
@role_required("commercial")
def villas():
    statut_filtre = request.args.get("statut", "")

    query = Villa.query
    if statut_filtre in STATUTS_VILLA:
        query = query.filter_by(statut=statut_filtre)

    liste_villas = query.order_by(Villa.numero).all()
    compteurs = {valeur: Villa.query.filter_by(statut=valeur).count() for valeur in STATUTS_VILLA}

    return render_template(
        "commercial/villas.html",
        villas=liste_villas,
        statuts_villa=STATUTS_VILLA,
        statuts_villa_couleur=STATUTS_VILLA_COULEUR,
        statuts_attribution=STATUTS_ATTRIBUTION_VILLA,
        statut_filtre=statut_filtre,
        compteurs=compteurs,
    )


@commercial_bp.route("/<int:client_id>/villas/nouvelle", methods=["POST"])
@role_required("commercial")
def villa_attribution_nouvelle(client_id):
    client = db.get_or_404(ClientCommercial, client_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas modifier une fiche client.", "warning")
        return redirect(url_for("commercial.liste"))

    villa_id = request.form.get("villa_id", type=int)
    villa = db.get_or_404(Villa, villa_id) if villa_id else None
    statut = request.form.get("statut", "")

    if not villa:
        flash("Merci de sélectionner une villa.", "danger")
        return redirect(url_for("commercial.modifier", client_id=client.id))
    if statut not in STATUTS_ATTRIBUTION_VILLA:
        flash("Le statut de la villa est invalide.", "danger")
        return redirect(url_for("commercial.modifier", client_id=client.id))

    if statut in ("reservee", "vendue"):
        deja_prise = VillaAttribution.query.filter(
            VillaAttribution.villa_id == villa.id,
            VillaAttribution.statut.in_(("reservee", "vendue")),
            VillaAttribution.client_id != client.id,
        ).first()
        if deja_prise:
            flash(f"{villa.label()} est déjà {STATUTS_ATTRIBUTION_VILLA[deja_prise.statut].lower()} par {deja_prise.client.nom_client}.", "danger")
            return redirect(url_for("commercial.modifier", client_id=client.id))

    db.session.add(VillaAttribution(
        villa_id=villa.id,
        client_id=client.id,
        statut=statut,
        date=_parse_date(request.form.get("date")),
        notes=request.form.get("notes", "").strip() or None,
    ))
    _recalculer_statut_villa(villa)
    db.session.commit()
    flash(f"{villa.label()} ajoutée à la fiche de {client.nom_client}.", "success")
    return redirect(url_for("commercial.modifier", client_id=client.id))


@commercial_bp.route("/villas/attributions/<int:attribution_id>/modifier", methods=["POST"])
@role_required("commercial")
def villa_attribution_modifier(attribution_id):
    attribution = db.get_or_404(VillaAttribution, attribution_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas modifier une fiche client.", "warning")
        return redirect(url_for("commercial.liste"))

    statut = request.form.get("statut", "")
    if statut not in STATUTS_ATTRIBUTION_VILLA:
        flash("Le statut de la villa est invalide.", "danger")
        return redirect(url_for("commercial.modifier", client_id=attribution.client_id))

    if statut in ("reservee", "vendue"):
        deja_prise = VillaAttribution.query.filter(
            VillaAttribution.villa_id == attribution.villa_id,
            VillaAttribution.statut.in_(("reservee", "vendue")),
            VillaAttribution.id != attribution.id,
            VillaAttribution.client_id != attribution.client_id,
        ).first()
        if deja_prise:
            flash(f"{attribution.villa.label()} est déjà {STATUTS_ATTRIBUTION_VILLA[deja_prise.statut].lower()} par {deja_prise.client.nom_client}.", "danger")
            return redirect(url_for("commercial.modifier", client_id=attribution.client_id))

    attribution.statut = statut
    attribution.date = _parse_date(request.form.get("date"))
    attribution.notes = request.form.get("notes", "").strip() or None
    _recalculer_statut_villa(attribution.villa)
    db.session.commit()
    flash("Villa mise à jour.", "success")
    return redirect(url_for("commercial.modifier", client_id=attribution.client_id))


@commercial_bp.route("/villas/attributions/<int:attribution_id>/supprimer", methods=["POST"])
@role_required("commercial")
def villa_attribution_supprimer(attribution_id):
    attribution = db.get_or_404(VillaAttribution, attribution_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas modifier une fiche client.", "warning")
        return redirect(url_for("commercial.liste"))

    client_id = attribution.client_id
    villa = attribution.villa
    db.session.delete(attribution)
    _recalculer_statut_villa(villa)
    db.session.commit()
    flash("Villa retirée de la fiche.", "info")
    return redirect(url_for("commercial.modifier", client_id=client_id))
