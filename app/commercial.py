from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user

from app import db
from app.models import ClientCommercial
from app.decorators import role_required
from app.constants import TYPES_CLIENT, STATUTS_CLIENT, STATUTS_CLIENT_COULEUR

commercial_bp = Blueprint("commercial", __name__, url_prefix="/commercial")

STATUTS_AVEC_RELANCE = {"rdv_cale", "a_relancer"}


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

    return erreurs


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
    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "commercial/form.html", client=None, form=request.form,
                types_client=TYPES_CLIENT, statuts_client=STATUTS_CLIENT,
            )

        type_client = request.form.get("type_client")
        statut = request.form.get("statut")
        db.session.add(ClientCommercial(
            date_contact=_parse_date(request.form.get("date_contact")),
            nom_client=request.form.get("nom_client", "").strip(),
            telephone=request.form.get("telephone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            type_client=type_client,
            type_client_precision=request.form.get("type_client_precision", "").strip() or None if type_client == "autre" else None,
            budget=_parse_decimal(request.form.get("budget")) if type_client == "investisseur" else None,
            villa_interessee=request.form.get("villa_interessee", "").strip() or None,
            statut=statut,
            prochaine_relance=_parse_date(request.form.get("prochaine_relance")) if statut in STATUTS_AVEC_RELANCE else None,
            notes=request.form.get("notes", "").strip() or None,
            cree_par_id=current_user.id,
        ))
        db.session.commit()
        flash("Client ajouté avec succès.", "success")
        return redirect(url_for("commercial.liste"))

    return render_template(
        "commercial/form.html", client=None, form={},
        types_client=TYPES_CLIENT, statuts_client=STATUTS_CLIENT,
    )


@commercial_bp.route("/<int:client_id>/modifier", methods=["GET", "POST"])
@role_required("commercial")
def modifier(client_id):
    client = db.get_or_404(ClientCommercial, client_id)

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "commercial/form.html", client=client, form=request.form,
                types_client=TYPES_CLIENT, statuts_client=STATUTS_CLIENT,
            )

        type_client = request.form.get("type_client")
        statut = request.form.get("statut")
        client.date_contact = _parse_date(request.form.get("date_contact"))
        client.nom_client = request.form.get("nom_client", "").strip()
        client.telephone = request.form.get("telephone", "").strip() or None
        client.email = request.form.get("email", "").strip() or None
        client.type_client = type_client
        client.type_client_precision = request.form.get("type_client_precision", "").strip() or None if type_client == "autre" else None
        client.budget = _parse_decimal(request.form.get("budget")) if type_client == "investisseur" else None
        client.villa_interessee = request.form.get("villa_interessee", "").strip() or None
        client.statut = statut
        client.prochaine_relance = _parse_date(request.form.get("prochaine_relance")) if statut in STATUTS_AVEC_RELANCE else None
        client.notes = request.form.get("notes", "").strip() or None
        db.session.commit()
        flash("Client modifié avec succès.", "success")
        return redirect(url_for("commercial.liste"))

    form = {
        "date_contact": client.date_contact.isoformat() if client.date_contact else "",
        "nom_client": client.nom_client,
        "telephone": client.telephone or "",
        "email": client.email or "",
        "type_client": client.type_client,
        "type_client_precision": client.type_client_precision or "",
        "budget": client.budget,
        "villa_interessee": client.villa_interessee or "",
        "statut": client.statut,
        "prochaine_relance": client.prochaine_relance.isoformat() if client.prochaine_relance else "",
        "notes": client.notes or "",
    }
    return render_template(
        "commercial/form.html", client=client, form=form,
        types_client=TYPES_CLIENT, statuts_client=STATUTS_CLIENT,
    )


@commercial_bp.route("/<int:client_id>/supprimer", methods=["POST"])
@role_required("commercial")
def supprimer(client_id):
    client = db.get_or_404(ClientCommercial, client_id)
    db.session.delete(client)
    db.session.commit()
    flash("Client supprimé.", "info")
    return redirect(url_for("commercial.liste"))
