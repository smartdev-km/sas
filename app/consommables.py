from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import func, extract
from app.decorators import role_required, admin_required

from app import db
from app.models import (
    Consommable, SuiviConsommable, Depense, ConfigCarburant, MouvementCarburant, DemandeCarburant,
    ArticleInventaire, MouvementInventaire, MouvementLitresCarburant, Deplacement,
)
from app.constants import PRIX_CARBURANT, CATEGORIES_INVENTAIRE, TYPES_GAZ, MOIS_FR

consommables_bp = Blueprint("consommables", __name__, url_prefix="/consommables")


def _config_carburant():
    config = ConfigCarburant.query.first()
    if not config:
        config = ConfigCarburant()
        db.session.add(config)
        db.session.commit()
    return config


def _stock_carburant():
    entrees = db.session.query(func.coalesce(func.sum(MouvementCarburant.quantite), 0)).filter_by(type_mouvement="reception").scalar()
    sorties = db.session.query(func.coalesce(func.sum(MouvementCarburant.quantite), 0)).filter_by(type_mouvement="utilisation").scalar()
    return int(entrees) - int(sorties)


def _suivi_du_mois(nom, date_mouvement, creer=False):
    """Suivi mensuel (interne) utilisé pour refléter le montant d'une catégorie
    (Carburant, Inventaire...) dans le budget Consommables global."""
    consommable = Consommable.query.filter(Consommable.nom.ilike(nom)).first()
    if not consommable:
        if not creer:
            return None
        consommable = Consommable(nom=nom, actif=True)
        db.session.add(consommable)
        db.session.flush()

    suivi = SuiviConsommable.query.filter_by(
        consommable_id=consommable.id, mois=date_mouvement.month, annee=date_mouvement.year
    ).first()
    if not suivi and creer:
        suivi = SuiviConsommable(
            consommable_id=consommable.id, mois=date_mouvement.month, annee=date_mouvement.year, montant=0
        )
        db.session.add(suivi)
        db.session.flush()
    return suivi


def _appliquer_montant(nom, date_mouvement, montant):
    """Ajoute le montant calculé au Suivi mensuel (catégorie donnée). Ignoré si ce mois est déjà validé."""
    suivi = _suivi_du_mois(nom, date_mouvement, creer=True)
    if suivi.valide:
        return False
    suivi.montant = float(suivi.montant) + montant
    return True


def _retirer_montant(nom, date_mouvement, montant):
    """Contrepartie de _appliquer_montant, utilisée lors de la suppression d'un mouvement."""
    suivi = _suivi_du_mois(nom, date_mouvement, creer=False)
    if not suivi or suivi.valide:
        return False
    suivi.montant = max(0, float(suivi.montant) - montant)
    return True


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


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


def _resume_article(article):
    achats = (
        db.session.query(
            func.coalesce(func.sum(MouvementInventaire.quantite), 0),
            func.coalesce(func.sum(MouvementInventaire.montant), 0),
        )
        .filter_by(article_id=article.id, type_mouvement="achat")
        .first()
    )
    utilise = db.session.query(func.coalesce(func.sum(MouvementInventaire.quantite), 0)).filter_by(
        article_id=article.id, type_mouvement="utilisation"
    ).scalar()

    achete = int(achats[0])
    prix_total = float(achats[1])
    utilise = int(utilise)
    return {"achete": achete, "prix_total": prix_total, "utilise": utilise, "reste": achete - utilise}


def _stock_article(article_id):
    achats = db.session.query(func.coalesce(func.sum(MouvementInventaire.quantite), 0)).filter_by(
        article_id=article_id, type_mouvement="achat"
    ).scalar()
    utilisations = db.session.query(func.coalesce(func.sum(MouvementInventaire.quantite), 0)).filter_by(
        article_id=article_id, type_mouvement="utilisation"
    ).scalar()
    return int(achats) - int(utilisations)


@consommables_bp.route("/")
@role_required("consommables")
def liste():
    categorie_filtre = request.args.get("categorie", "")
    mois_filtre = request.args.get("mois", type=int)
    annee_filtre = request.args.get("annee", type=int)

    query = ArticleInventaire.query.filter_by(actif=True)
    if categorie_filtre in CATEGORIES_INVENTAIRE:
        query = query.filter_by(categorie=categorie_filtre)
    articles = query.order_by(ArticleInventaire.categorie, ArticleInventaire.nom).all()

    lignes = []
    for article in articles:
        resume = _resume_article(article)
        lignes.append({
            "article": article,
            "stock_bas": article.seuil_alerte > 0 and resume["reste"] <= article.seuil_alerte,
            **resume,
        })

    prix_total_general = sum(l["prix_total"] for l in lignes)
    budget_alloue, budget_depense, budget_restant = _budget()

    mouvements_query = MouvementInventaire.query.join(ArticleInventaire)
    if mois_filtre:
        mouvements_query = mouvements_query.filter(extract("month", MouvementInventaire.date) == mois_filtre)
    if annee_filtre:
        mouvements_query = mouvements_query.filter(extract("year", MouvementInventaire.date) == annee_filtre)
    mouvements = (
        mouvements_query.order_by(MouvementInventaire.date.desc(), MouvementInventaire.id.desc())
        .limit(200)
        .all()
    )

    stock_carburant_bas = _stock_carburant() <= _config_carburant().seuil_alerte

    return render_template(
        "consommables/liste.html",
        lignes=lignes,
        mouvements=mouvements,
        categories=CATEGORIES_INVENTAIRE,
        categorie_filtre=categorie_filtre,
        prix_total_general=prix_total_general,
        budget_alloue=budget_alloue,
        budget_depense=budget_depense,
        budget_restant=budget_restant,
        stock_bas=stock_carburant_bas,
        today=date.today().isoformat(),
        mois_fr=MOIS_FR,
        mois_filtre=mois_filtre,
        annee_filtre=annee_filtre,
        annees=range(date.today().year - 2, date.today().year + 2),
    )


@consommables_bp.route("/articles/nouveau", methods=["POST"])
@role_required("consommables")
def article_nouveau():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter d'article directement.", "warning")
        return redirect(url_for("consommables.liste"))

    nom = request.form.get("nom", "").strip()
    categorie = request.form.get("categorie", "")
    seuil_brut = request.form.get("seuil_alerte", "").strip()

    if not nom:
        flash("Le nom est obligatoire.", "danger")
        return redirect(url_for("consommables.liste"))
    if categorie not in CATEGORIES_INVENTAIRE:
        flash("La catégorie sélectionnée est invalide.", "danger")
        return redirect(url_for("consommables.liste"))
    try:
        seuil_alerte = int(seuil_brut) if seuil_brut else 0
        if seuil_alerte < 0:
            raise ValueError
    except ValueError:
        flash("Le seuil d'alerte doit être un nombre entier positif ou nul.", "danger")
        return redirect(url_for("consommables.liste"))

    if ArticleInventaire.query.filter(
        ArticleInventaire.nom.ilike(nom), ArticleInventaire.categorie == categorie
    ).first():
        flash(f"« {nom} » existe déjà dans cette catégorie.", "danger")
    else:
        db.session.add(ArticleInventaire(nom=nom, categorie=categorie, seuil_alerte=seuil_alerte))
        db.session.commit()
        flash(f"« {nom} » ajouté à l'inventaire.", "success")

    return redirect(url_for("consommables.liste", categorie=categorie))


@consommables_bp.route("/articles/<int:article_id>/supprimer", methods=["POST"])
@role_required("consommables")
def article_supprimer(article_id):
    article = db.get_or_404(ArticleInventaire, article_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas supprimer d'article directement.", "warning")
        return redirect(url_for("consommables.liste"))

    if MouvementInventaire.query.filter_by(article_id=article.id).first():
        flash(f"Impossible de supprimer « {article.nom} » : des mouvements existent déjà pour cet article.", "danger")
        return redirect(url_for("consommables.liste"))

    db.session.delete(article)
    db.session.commit()
    flash(f"« {article.nom} » supprimé.", "info")
    return redirect(url_for("consommables.liste"))


@consommables_bp.route("/articles/<int:article_id>/mouvements/nouveau", methods=["POST"])
@role_required("consommables")
def article_mouvement_nouveau(article_id):
    article = db.get_or_404(ArticleInventaire, article_id)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas enregistrer de mouvement d'inventaire.", "warning")
        return redirect(url_for("consommables.liste"))

    type_mouvement = request.form.get("type_mouvement")
    if type_mouvement not in ("achat", "utilisation"):
        flash("Type de mouvement invalide.", "danger")
        return redirect(url_for("consommables.liste"))

    quantite_brute = request.form.get("quantite", "").strip()
    try:
        quantite = int(quantite_brute)
        if quantite <= 0:
            raise ValueError
    except ValueError:
        flash("La quantité doit être un nombre entier positif.", "danger")
        return redirect(url_for("consommables.liste"))

    if type_mouvement == "utilisation" and quantite > _stock_article(article.id):
        flash("Impossible d'enregistrer cette sortie : la quantité dépasse le stock disponible.", "danger")
        return redirect(url_for("consommables.liste"))

    date_valeur = _parse_date(request.form.get("date")) or date.today()

    prix_unitaire = None
    montant = None
    if type_mouvement == "achat":
        prix_unitaire_brut = request.form.get("prix_unitaire", "").strip()
        try:
            prix_unitaire = float(prix_unitaire_brut)
            if prix_unitaire <= 0:
                raise ValueError
        except ValueError:
            flash("Le prix unitaire doit être un nombre positif.", "danger")
            return redirect(url_for("consommables.liste"))
        montant = round(quantite * prix_unitaire, 2)

    mouvement = MouvementInventaire(
        article_id=article.id,
        date=date_valeur,
        type_mouvement=type_mouvement,
        quantite=quantite,
        prix_unitaire=prix_unitaire,
        montant=montant,
        beneficiaire=request.form.get("beneficiaire", "").strip() or None,
        notes=request.form.get("notes", "").strip() or None,
        enregistre_par_id=current_user.id,
    )
    db.session.add(mouvement)

    if montant:
        if _appliquer_montant("Inventaire", date_valeur, montant):
            flash(f"Achat enregistré. {montant:.0f} KMF ajoutés au Suivi mensuel (Inventaire).", "success")
        else:
            flash(
                "Achat enregistré, mais le Suivi mensuel d'Inventaire pour ce mois est déjà validé : "
                "ajoutez le montant manuellement après déverrouillage.",
                "warning",
            )
        db.session.commit()
    else:
        db.session.commit()
        flash("Sortie de stock enregistrée.", "success")

    return redirect(url_for("consommables.liste"))


@consommables_bp.route("/mouvements/<int:mouvement_id>/supprimer", methods=["POST"])
@role_required("consommables")
def article_mouvement_supprimer(mouvement_id):
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas supprimer de mouvement d'inventaire.", "warning")
        return redirect(url_for("consommables.liste"))

    mouvement = db.get_or_404(MouvementInventaire, mouvement_id)

    if mouvement.montant:
        if not _retirer_montant("Inventaire", mouvement.date, float(mouvement.montant)):
            flash(
                "Mouvement supprimé, mais le Suivi mensuel d'Inventaire pour ce mois est déjà validé : "
                "retirez le montant manuellement après déverrouillage.",
                "warning",
            )

    db.session.delete(mouvement)
    db.session.commit()
    flash("Mouvement supprimé.", "info")
    return redirect(url_for("consommables.liste"))


# --- Carburant ------------------------------------------------------------

def _resume_litres(type_gaz):
    achats = (
        db.session.query(
            func.coalesce(func.sum(MouvementLitresCarburant.quantite_litres), 0),
            func.coalesce(func.sum(MouvementLitresCarburant.montant), 0),
        )
        .filter_by(type_gaz=type_gaz, type_mouvement="achat")
        .first()
    )
    utilise = db.session.query(func.coalesce(func.sum(MouvementLitresCarburant.quantite_litres), 0)).filter_by(
        type_gaz=type_gaz, type_mouvement="utilisation"
    ).scalar()

    achete = float(achats[0])
    prix_total = float(achats[1])
    utilise = float(utilise)
    reste = achete - utilise

    # Valeur de ce qui a été utilisé / reste, au prorata du prix moyen payé à l'achat.
    prix_utilise = round(prix_total * utilise / achete, 2) if achete else 0.0
    prix_restant = round(prix_total - prix_utilise, 2)

    return {
        "achete": achete, "prix_total": prix_total, "utilise": utilise, "reste": reste,
        "prix_utilise": prix_utilise, "prix_restant": prix_restant,
    }


def _stock_litres(type_gaz):
    return _resume_litres(type_gaz)["reste"]


def _budget_carburant():
    """Total des dépenses validées de catégorie « Carburant » (budget alloué par l'admin)."""
    return float(
        db.session.query(func.sum(Depense.montant))
        .filter(Depense.categorie == "Carburant", Depense.valide.is_(True))
        .scalar() or 0
    )


@consommables_bp.route("/carburant")
@role_required("consommables")
def carburant():
    mois_filtre = request.args.get("mois", type=int)
    annee_filtre = request.args.get("annee", type=int)

    config = _config_carburant()
    stock = _stock_carburant()
    mouvements = (
        MouvementCarburant.query.order_by(MouvementCarburant.date.desc(), MouvementCarburant.id.desc())
        .limit(50)
        .all()
    )
    demandes = DemandeCarburant.query.order_by(DemandeCarburant.date_demande.desc()).limit(20).all()
    demande_en_attente = DemandeCarburant.query.filter_by(statut="en_attente").first()

    lignes_litres = [
        {"type_gaz": valeur, "libelle": libelle, **_resume_litres(valeur)}
        for valeur, libelle in TYPES_GAZ.items()
    ]
    mouvements_litres_query = MouvementLitresCarburant.query
    if mois_filtre:
        mouvements_litres_query = mouvements_litres_query.filter(extract("month", MouvementLitresCarburant.date) == mois_filtre)
    if annee_filtre:
        mouvements_litres_query = mouvements_litres_query.filter(extract("year", MouvementLitresCarburant.date) == annee_filtre)
    mouvements_litres = (
        mouvements_litres_query.order_by(MouvementLitresCarburant.date.desc(), MouvementLitresCarburant.id.desc())
        .limit(200)
        .all()
    )

    return render_template(
        "consommables/carburant.html",
        stock=stock,
        seuil=config.seuil_alerte,
        stock_bas=stock <= config.seuil_alerte,
        mouvements=mouvements,
        demandes=demandes,
        demande_en_attente=demande_en_attente,
        today=date.today().isoformat(),
        prix_carburant=PRIX_CARBURANT,
        lignes_litres=lignes_litres,
        mouvements_litres=mouvements_litres,
        types_gaz=TYPES_GAZ,
        budget_carburant=_budget_carburant(),
        prix_total_utilise=sum(l["prix_utilise"] for l in lignes_litres),
        prix_total_restant=sum(l["prix_restant"] for l in lignes_litres),
        mois_fr=MOIS_FR,
        mois_filtre=mois_filtre,
        annee_filtre=annee_filtre,
        annees=range(date.today().year - 2, date.today().year + 2),
    )


@consommables_bp.route("/carburant/mouvements/nouveau", methods=["POST"])
@role_required("consommables")
def carburant_mouvement_nouveau():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas enregistrer de mouvement de carburant.", "warning")
        return redirect(url_for("consommables.carburant"))

    type_mouvement = request.form.get("type_mouvement")
    if type_mouvement not in ("reception", "utilisation"):
        flash("Type de mouvement invalide.", "danger")
        return redirect(url_for("consommables.carburant"))

    quantite_brute = request.form.get("quantite", "").strip()
    try:
        quantite = int(quantite_brute)
        if quantite <= 0:
            raise ValueError
    except ValueError:
        flash("La quantité doit être un nombre entier positif.", "danger")
        return redirect(url_for("consommables.carburant"))

    if type_mouvement == "utilisation" and quantite > _stock_carburant():
        flash("Impossible d'enregistrer cette sortie : la quantité dépasse le stock disponible.", "danger")
        return redirect(url_for("consommables.carburant"))

    date_valeur = _parse_date(request.form.get("date")) or date.today()

    mouvement = MouvementCarburant(
        date=date_valeur,
        type_mouvement=type_mouvement,
        quantite=quantite,
        beneficiaire=request.form.get("beneficiaire", "").strip() or None,
        notes=request.form.get("notes", "").strip() or None,
        enregistre_par_id=current_user.id,
    )
    db.session.add(mouvement)
    db.session.commit()
    flash("Mouvement de tickets enregistré.", "success")

    return redirect(url_for("consommables.carburant"))


@consommables_bp.route("/carburant/mouvements/<int:mouvement_id>/supprimer", methods=["POST"])
@role_required("consommables")
def carburant_mouvement_supprimer(mouvement_id):
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas supprimer de mouvement de carburant.", "warning")
        return redirect(url_for("consommables.carburant"))

    mouvement = db.get_or_404(MouvementCarburant, mouvement_id)

    if mouvement.montant:
        if not _retirer_montant("Carburant", mouvement.date, float(mouvement.montant)):
            flash(
                "Mouvement supprimé, mais le Suivi mensuel de Carburant pour ce mois est déjà validé : "
                "retirez le montant manuellement après déverrouillage.",
                "warning",
            )

    db.session.delete(mouvement)
    db.session.commit()
    flash("Mouvement supprimé.", "info")
    return redirect(url_for("consommables.carburant"))


@consommables_bp.route("/carburant/litres/utilisation", methods=["POST"])
@role_required("consommables")
def carburant_litres_utilisation():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas enregistrer de mouvement de carburant.", "warning")
        return redirect(url_for("consommables.carburant"))

    type_gaz = request.form.get("type_gaz")
    if type_gaz not in TYPES_GAZ:
        flash("Type de gaz invalide.", "danger")
        return redirect(url_for("consommables.carburant"))

    quantite_brute = request.form.get("quantite_litres", "").strip()
    try:
        quantite_litres = float(quantite_brute)
        if quantite_litres <= 0:
            raise ValueError
    except ValueError:
        flash("La quantité de litres doit être un nombre positif.", "danger")
        return redirect(url_for("consommables.carburant"))

    if quantite_litres > _stock_litres(type_gaz):
        flash("Impossible d'enregistrer cette sortie : la quantité dépasse le stock de litres disponible.", "danger")
        return redirect(url_for("consommables.carburant"))

    date_valeur = _parse_date(request.form.get("date")) or date.today()

    db.session.add(MouvementLitresCarburant(
        date=date_valeur,
        type_mouvement="utilisation",
        type_gaz=type_gaz,
        quantite_litres=quantite_litres,
        beneficiaire=request.form.get("beneficiaire", "").strip() or None,
        notes=request.form.get("notes", "").strip() or None,
        enregistre_par_id=current_user.id,
    ))
    db.session.commit()
    flash("Utilisation de carburant (litres) enregistrée.", "success")
    return redirect(url_for("consommables.carburant"))


@consommables_bp.route("/carburant/litres/<int:mouvement_id>/supprimer", methods=["POST"])
@role_required("consommables")
def carburant_litres_supprimer(mouvement_id):
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas supprimer de mouvement de carburant.", "warning")
        return redirect(url_for("consommables.carburant"))

    mouvement = db.get_or_404(MouvementLitresCarburant, mouvement_id)

    if mouvement.type_mouvement == "achat":
        flash("Cet achat provient d'une dépense « Carburant » ; modifiez-le ou supprimez-le depuis Dépenses.", "warning")
        return redirect(url_for("consommables.carburant"))

    db.session.delete(mouvement)
    db.session.commit()
    flash("Mouvement supprimé.", "info")
    return redirect(url_for("consommables.carburant"))


@consommables_bp.route("/carburant/seuil", methods=["POST"])
@role_required("consommables")
def carburant_seuil():
    seuil_brut = request.form.get("seuil_alerte", "").strip()
    try:
        seuil = int(seuil_brut)
        if seuil < 0:
            raise ValueError
    except ValueError:
        flash("Le seuil doit être un nombre entier positif ou nul.", "danger")
        return redirect(url_for("consommables.carburant"))

    config = _config_carburant()
    config.seuil_alerte = seuil
    db.session.commit()
    flash("Seuil d'alerte mis à jour.", "success")
    return redirect(url_for("consommables.carburant"))


@consommables_bp.route("/carburant/demandes/nouvelle", methods=["POST"])
@role_required("consommables")
def carburant_demande_nouvelle():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas faire de demande de carburant.", "warning")
        return redirect(url_for("consommables.carburant"))

    if DemandeCarburant.query.filter_by(statut="en_attente").first():
        flash("Une demande de réapprovisionnement est déjà en attente.", "info")
        return redirect(url_for("consommables.carburant"))

    db.session.add(DemandeCarburant(
        demande_par_id=current_user.id,
        stock_au_moment=_stock_carburant(),
        notes=request.form.get("notes", "").strip() or None,
    ))
    db.session.commit()
    flash("Demande de réapprovisionnement envoyée à l'administration.", "success")
    return redirect(url_for("consommables.carburant"))


@consommables_bp.route("/carburant/demandes/<int:demande_id>/traiter", methods=["POST"])
@admin_required
def carburant_demande_traiter(demande_id):
    demande = db.get_or_404(DemandeCarburant, demande_id)
    if demande.statut != "en_attente":
        flash("Cette demande a déjà été traitée.", "info")
    else:
        demande.statut = "traitee"
        demande.traite_le = datetime.now()
        demande.traite_par_id = current_user.id
        db.session.commit()
        flash("Demande marquée comme traitée. Pensez à enregistrer la réception des nouveaux tickets.", "success")
    return redirect(url_for("consommables.carburant"))


@consommables_bp.route("/carburant/demandes/<int:demande_id>/rejeter", methods=["POST"])
@admin_required
def carburant_demande_rejeter(demande_id):
    demande = db.get_or_404(DemandeCarburant, demande_id)
    if demande.statut != "en_attente":
        flash("Cette demande a déjà été traitée.", "info")
    else:
        demande.statut = "rejetee"
        demande.traite_le = datetime.now()
        demande.traite_par_id = current_user.id
        db.session.commit()
        flash("Demande rejetée.", "info")
    return redirect(url_for("consommables.carburant"))


# --- Déplacement ------------------------------------------------------------

@consommables_bp.route("/deplacement")
@role_required("consommables")
def deplacement():
    mois_filtre = request.args.get("mois", type=int)
    annee_filtre = request.args.get("annee", type=int)

    query = Deplacement.query
    if mois_filtre:
        query = query.filter(extract("month", Deplacement.date) == mois_filtre)
    if annee_filtre:
        query = query.filter(extract("year", Deplacement.date) == annee_filtre)
    deplacements = query.order_by(Deplacement.date.desc(), Deplacement.id.desc()).limit(200).all()
    total = sum(float(d.prix) for d in deplacements)
    budget_alloue, budget_depense, budget_restant = _budget()

    return render_template(
        "consommables/deplacement.html",
        deplacements=deplacements,
        total=total,
        budget_alloue=budget_alloue,
        budget_depense=budget_depense,
        budget_restant=budget_restant,
        stock_bas=_stock_carburant() <= _config_carburant().seuil_alerte,
        today=date.today().isoformat(),
        mois_fr=MOIS_FR,
        mois_filtre=mois_filtre,
        annee_filtre=annee_filtre,
        annees=range(date.today().year - 2, date.today().year + 2),
    )


@consommables_bp.route("/deplacement/nouveau", methods=["POST"])
@role_required("consommables")
def deplacement_nouveau():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter de déplacement directement.", "warning")
        return redirect(url_for("consommables.deplacement"))

    trajet = request.form.get("trajet", "").strip()
    if not trajet:
        flash("Le trajet est obligatoire.", "danger")
        return redirect(url_for("consommables.deplacement"))

    prix_brut = request.form.get("prix", "").strip()
    try:
        prix = float(prix_brut)
        if prix <= 0:
            raise ValueError
    except ValueError:
        flash("Le prix doit être un nombre positif.", "danger")
        return redirect(url_for("consommables.deplacement"))

    date_valeur = _parse_date(request.form.get("date")) or date.today()

    db.session.add(Deplacement(
        date=date_valeur,
        trajet=trajet,
        prix=prix,
        notes=request.form.get("notes", "").strip() or None,
        enregistre_par_id=current_user.id,
    ))

    if _appliquer_montant("Déplacement", date_valeur, prix):
        flash("Déplacement enregistré.", "success")
    else:
        flash(
            "Déplacement enregistré, mais le Suivi mensuel de Déplacement pour ce mois est déjà validé : "
            "ajoutez le montant manuellement après déverrouillage.",
            "warning",
        )
    db.session.commit()

    return redirect(url_for("consommables.deplacement"))


@consommables_bp.route("/deplacement/<int:deplacement_id>/supprimer", methods=["POST"])
@role_required("consommables")
def deplacement_supprimer(deplacement_id):
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas supprimer de déplacement directement.", "warning")
        return redirect(url_for("consommables.deplacement"))

    trajet = db.get_or_404(Deplacement, deplacement_id)

    if not _retirer_montant("Déplacement", trajet.date, float(trajet.prix)):
        flash(
            "Déplacement supprimé, mais le Suivi mensuel de Déplacement pour ce mois est déjà validé : "
            "retirez le montant manuellement après déverrouillage.",
            "warning",
        )

    db.session.delete(trajet)
    db.session.commit()
    flash("Déplacement supprimé.", "info")
    return redirect(url_for("consommables.deplacement"))
