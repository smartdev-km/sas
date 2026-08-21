from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from app.decorators import admin_required, espace_employe_required

from app import db
from app.models import Appareil, Employe, DemandeAppareil, Depense, HistoriqueAppareil
from app.constants import TYPES_APPAREIL, STATUTS_APPAREIL, STATUTS_DEMANDE_APPAREIL, TYPES_HISTORIQUE_APPAREIL

appareils_bp = Blueprint("appareils", __name__, url_prefix="/appareils")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _employe_id_courant():
    """Retourne l'id Employe de l'utilisateur connecté (lui-même, ou l'employé lié
    pour un compte comptable/secrétaire)."""
    if current_user.is_admin_account:
        return current_user.employe_id
    return current_user.id


def _log_historique(appareil_id, type_evenement, description=None):
    db.session.add(HistoriqueAppareil(
        appareil_id=appareil_id, type_evenement=type_evenement, description=description,
    ))


@appareils_bp.route("/")
@admin_required
def liste():
    statut = request.args.get("statut") or "en_service"
    employe_id = request.args.get("employe_id", type=int)

    query = Appareil.query
    if statut == "en_stock":
        query = query.filter(Appareil.employe_id.is_(None))
    elif statut == "en_service":
        query = query.filter(Appareil.statut == statut, Appareil.employe_id.isnot(None))
    else:
        query = query.filter(Appareil.statut == statut)
    if employe_id:
        query = query.filter(Appareil.employe_id == employe_id)

    appareils = query.order_by(Appareil.created_at.desc()).all()
    employes = Employe.query.order_by(Employe.nom).all()

    demandes_en_attente = {
        d.appareil_id: d
        for d in DemandeAppareil.query.filter_by(statut="en_attente").all()
    }

    compteurs = {}
    for valeur in STATUTS_APPAREIL:
        compteurs[valeur] = Appareil.query.filter_by(statut=valeur).count()
    compteurs["en_service"] = Appareil.query.filter_by(statut="en_service").filter(Appareil.employe_id.isnot(None)).count()
    compteurs["en_stock"] = Appareil.query.filter(Appareil.employe_id.is_(None)).count()

    return render_template(
        "appareils/liste.html",
        appareils=appareils,
        employes=employes,
        statuts=STATUTS_APPAREIL,
        demandes_en_attente=demandes_en_attente,
        compteurs=compteurs,
        filtres={"statut": statut, "employe_id": employe_id},
    )


@appareils_bp.route("/nouveau", methods=["GET", "POST"])
@admin_required
def nouveau():
    employes = Employe.query.filter_by(actif=True).order_by(Employe.nom).all()

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "appareils/form.html", appareil=None, form=request.form,
                employes=employes, types=TYPES_APPAREIL, historique=[], types_historique=TYPES_HISTORIQUE_APPAREIL,
            )

        appareil = Appareil(
            type_appareil=request.form.get("type_appareil"),
            marque=request.form.get("marque", "").strip() or None,
            modele=request.form.get("modele", "").strip() or None,
            numero_serie=request.form.get("numero_serie", "").strip() or None,
            employe_id=request.form.get("employe_id", type=int) or None,
            date_attribution=_parse_date(request.form.get("date_attribution")),
            notes=request.form.get("notes", "").strip() or None,
            statut="en_service",
        )
        db.session.add(appareil)
        db.session.flush()

        description = f"Attribué à {appareil.employe.nom}" if appareil.employe_id else "Ajouté en stock"
        _log_historique(appareil.id, "creation", description)

        db.session.commit()
        flash("Appareil ajouté avec succès.", "success")
        return redirect(url_for("appareils.liste"))

    return render_template(
        "appareils/form.html", appareil=None, form={}, employes=employes, types=TYPES_APPAREIL,
        historique=[], types_historique=TYPES_HISTORIQUE_APPAREIL,
    )


@appareils_bp.route("/<int:appareil_id>/modifier", methods=["GET", "POST"])
@admin_required
def modifier(appareil_id):
    appareil = db.get_or_404(Appareil, appareil_id)
    employes = Employe.query.filter_by(actif=True).order_by(Employe.nom).all()

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "appareils/form.html", appareil=appareil, form=request.form,
                employes=employes, types=TYPES_APPAREIL,
                historique=appareil.historique, types_historique=TYPES_HISTORIQUE_APPAREIL,
            )

        ancien_employe_id = appareil.employe_id
        nouvel_employe_id = request.form.get("employe_id", type=int) or None

        appareil.type_appareil = request.form.get("type_appareil")
        appareil.marque = request.form.get("marque", "").strip() or None
        appareil.modele = request.form.get("modele", "").strip() or None
        appareil.numero_serie = request.form.get("numero_serie", "").strip() or None
        appareil.employe_id = nouvel_employe_id
        appareil.date_attribution = _parse_date(request.form.get("date_attribution"))
        appareil.notes = request.form.get("notes", "").strip() or None

        if nouvel_employe_id != ancien_employe_id:
            if nouvel_employe_id:
                _log_historique(appareil.id, "attribution", f"Attribué à {appareil.employe.nom}")
            else:
                _log_historique(appareil.id, "attribution", "Retiré de son attribution — remis en stock")

        db.session.commit()
        flash("Appareil modifié avec succès.", "success")
        return redirect(url_for("appareils.liste"))

    form = {
        "type_appareil": appareil.type_appareil,
        "marque": appareil.marque or "",
        "modele": appareil.modele or "",
        "numero_serie": appareil.numero_serie or "",
        "employe_id": appareil.employe_id,
        "date_attribution": appareil.date_attribution.isoformat() if appareil.date_attribution else "",
        "notes": appareil.notes or "",
    }
    return render_template(
        "appareils/form.html", appareil=appareil, form=form, employes=employes, types=TYPES_APPAREIL,
        historique=appareil.historique, types_historique=TYPES_HISTORIQUE_APPAREIL,
    )


@appareils_bp.route("/<int:appareil_id>/endommager", methods=["POST"])
@admin_required
def endommager(appareil_id):
    appareil = db.get_or_404(Appareil, appareil_id)
    if appareil.statut != "en_service":
        flash("Seul un appareil en service peut être marqué comme endommagé.", "danger")
        return redirect(url_for("appareils.liste"))

    note = request.form.get("note", "").strip()
    appareil.statut = "endommage"
    _log_historique(appareil.id, "endommage", note or None)
    db.session.commit()
    flash("Appareil marqué comme endommagé.", "warning")
    return redirect(url_for("appareils.liste"))


@appareils_bp.route("/<int:appareil_id>/hors-service", methods=["POST"])
@admin_required
def hors_service(appareil_id):
    appareil = db.get_or_404(Appareil, appareil_id)
    appareil.statut = "hors_service"
    _log_historique(appareil.id, "hors_service")
    db.session.commit()
    flash("Appareil marqué hors service.", "info")
    return redirect(url_for("appareils.liste"))


@appareils_bp.route("/<int:appareil_id>/remplacer", methods=["GET", "POST"])
@admin_required
def remplacer(appareil_id):
    ancien = db.get_or_404(Appareil, appareil_id)
    if ancien.statut != "endommage":
        flash("Seul un appareil endommagé peut être remplacé.", "danger")
        return redirect(url_for("appareils.liste"))

    if request.method == "POST":
        erreurs = _valider_formulaire(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("appareils/remplacer.html", ancien=ancien, form=request.form, types=TYPES_APPAREIL)

        nouveau = Appareil(
            type_appareil=request.form.get("type_appareil"),
            marque=request.form.get("marque", "").strip() or None,
            modele=request.form.get("modele", "").strip() or None,
            numero_serie=request.form.get("numero_serie", "").strip() or None,
            employe_id=ancien.employe_id,
            date_attribution=date.today(),
            notes=request.form.get("notes", "").strip() or None,
            statut="en_service",
        )
        db.session.add(nouveau)
        db.session.flush()

        ancien.statut = "remplace"
        ancien.remplace_par_id = nouveau.id

        libelle_nouveau = " ".join(filter(None, [nouveau.marque, nouveau.modele])) or nouveau.type_appareil
        _log_historique(ancien.id, "remplacement", f"Remplacé par {libelle_nouveau}")
        _log_historique(nouveau.id, "creation", f"Créé en remplacement de l'appareil #{ancien.id}")

        demande_ouverte = DemandeAppareil.query.filter_by(appareil_id=ancien.id, statut="en_attente").first()
        if demande_ouverte:
            demande_ouverte.statut = "traitee"
            demande_ouverte.date_traitement = datetime.now()

        db.session.commit()
        flash("Remplacement enregistré avec succès.", "success")
        return redirect(url_for("appareils.liste"))

    form = {
        "type_appareil": ancien.type_appareil,
        "marque": "",
        "modele": "",
        "numero_serie": "",
        "notes": "",
    }
    return render_template("appareils/remplacer.html", ancien=ancien, form=form, types=TYPES_APPAREIL)


@appareils_bp.route("/<int:appareil_id>/reparer", methods=["GET", "POST"])
@admin_required
def reparer(appareil_id):
    appareil = db.get_or_404(Appareil, appareil_id)
    if appareil.statut != "endommage":
        flash("Seul un appareil endommagé peut être marqué comme réparé.", "danger")
        return redirect(url_for("appareils.liste"))

    employes = Employe.query.filter_by(actif=True).order_by(Employe.nom).all()

    if request.method == "POST":
        montant_brut = request.form.get("montant_reparation", "").strip()
        try:
            montant_reparation = float(montant_brut) if montant_brut else 0
            if montant_reparation < 0:
                raise ValueError
        except ValueError:
            flash("Le montant de la réparation est invalide.", "danger")
            return render_template("appareils/reparer.html", appareil=appareil, employes=employes, form=request.form)

        attribution = request.form.get("attribution", "stock")
        nouvel_employe_id = None
        if attribution == "employe":
            nouvel_employe_id = request.form.get("employe_id", type=int)
            if not nouvel_employe_id:
                flash("Sélectionnez un employé, ou choisissez « Remettre en stock ».", "danger")
                return render_template("appareils/reparer.html", appareil=appareil, employes=employes, form=request.form)

        appareil.statut = "en_service"
        appareil.employe_id = nouvel_employe_id
        if nouvel_employe_id:
            appareil.date_attribution = date.today()

        if montant_reparation > 0:
            description = f"Coût : {montant_reparation:,.0f} KMF".replace(",", " ")
        else:
            description = "Aucun coût enregistré"
        if nouvel_employe_id:
            description += f" — Attribué à {appareil.employe.nom}"
        else:
            description += " — Remis en stock"
        _log_historique(appareil.id, "reparation", description)

        if montant_reparation > 0:
            depense_description = f"Réparation {appareil.type_appareil}"
            if appareil.marque:
                depense_description += f" {appareil.marque}"
            depense_description += f" (#{appareil.id})"
            db.session.add(Depense(
                date=date.today(),
                montant=montant_reparation,
                categorie="Réparation",
                description=depense_description,
            ))

        demande_ouverte = DemandeAppareil.query.filter_by(appareil_id=appareil.id, statut="en_attente").first()
        if demande_ouverte:
            demande_ouverte.statut = "traitee"
            demande_ouverte.date_traitement = datetime.now()

        db.session.commit()
        flash("Appareil marqué comme réparé.", "success")
        return redirect(url_for("appareils.liste"))

    return render_template(
        "appareils/reparer.html", appareil=appareil, employes=employes,
        form={"attribution": "stock", "employe_id": appareil.employe_id},
    )


@appareils_bp.route("/<int:appareil_id>/rejeter-demande", methods=["POST"])
@admin_required
def rejeter_demande(appareil_id):
    appareil = db.get_or_404(Appareil, appareil_id)
    demande = DemandeAppareil.query.filter_by(appareil_id=appareil.id, statut="en_attente").first()
    if not demande:
        flash("Aucune demande en attente pour cet appareil.", "danger")
        return redirect(url_for("appareils.liste"))

    demande.statut = "rejetee"
    demande.date_traitement = datetime.now()
    if appareil.statut == "endommage":
        appareil.statut = "en_service"
    _log_historique(appareil.id, "rejet", "Demande de remplacement rejetée, appareil remis en service")
    db.session.commit()
    flash("Demande rejetée, l'appareil est remis en service.", "info")
    return redirect(url_for("appareils.liste"))


@appareils_bp.route("/<int:appareil_id>/supprimer", methods=["POST"])
@admin_required
def supprimer(appareil_id):
    appareil = db.get_or_404(Appareil, appareil_id)
    if appareil.remplace_par_id or appareil.remplace:
        flash("Impossible de supprimer cet appareil : il fait partie d'un historique de remplacement. Utilisez « Hors service » à la place.", "danger")
        return redirect(url_for("appareils.liste"))

    db.session.delete(appareil)
    db.session.commit()
    flash("Appareil supprimé.", "info")
    return redirect(url_for("appareils.liste"))


def _valider_formulaire(form):
    erreurs = []
    if not form.get("type_appareil", "").strip():
        erreurs.append("Le type d'appareil est obligatoire.")
    return erreurs


# --- Espace employé (portail dédié + comptes comptable/secrétaire) --------

@appareils_bp.route("/mes-appareils")
@espace_employe_required
def mes_appareils():
    employe_id = _employe_id_courant()
    appareils = (
        Appareil.query.filter_by(employe_id=employe_id).order_by(Appareil.created_at.desc()).all()
        if employe_id else []
    )
    demandes_en_attente = {
        d.appareil_id: d
        for d in DemandeAppareil.query.filter_by(statut="en_attente").all()
    }
    return render_template(
        "appareils/mes_appareils.html",
        appareils=appareils,
        statuts=STATUTS_APPAREIL,
        demandes_en_attente=demandes_en_attente,
    )


@appareils_bp.route("/<int:appareil_id>/demander-remplacement", methods=["POST"])
@espace_employe_required
def demander_remplacement(appareil_id):
    employe_id = _employe_id_courant()
    appareil = db.get_or_404(Appareil, appareil_id)

    if employe_id is None or appareil.employe_id != employe_id:
        abort(403)

    if appareil.statut != "en_service":
        flash("Cet appareil n'est pas actuellement en service.", "danger")
        return redirect(url_for("appareils.mes_appareils"))

    description = request.form.get("description", "").strip()
    if not description:
        flash("Merci de décrire le problème rencontré.", "danger")
        return redirect(url_for("appareils.mes_appareils"))

    appareil.statut = "endommage"
    _log_historique(appareil.id, "demande", description)

    db.session.add(DemandeAppareil(appareil_id=appareil.id, description=description, statut="en_attente"))
    db.session.commit()
    flash("Votre demande de remplacement a été envoyée à l'administrateur.", "success")
    return redirect(url_for("appareils.mes_appareils"))
