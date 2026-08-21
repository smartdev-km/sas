from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.decorators import admin_required, role_required
from sqlalchemy import func

from app import db
from app.models import Employe, Salaire, User, ConnexionLog, TransactionBancaire
from app.constants import MOIS_FR, STATUTS_SALAIRE, SEXES, TYPES_CONTRAT, MODES_PAIEMENT, ROLES_COMPTE
from app.presence import calculer_presence_mensuelle, statistiques_annuelles_employe

salaires_bp = Blueprint("salaires", __name__, url_prefix="/salaires")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


# --- Employés ---------------------------------------------------------

@salaires_bp.route("/employes")
@role_required("salaires")
def employes():
    liste = Employe.query.order_by(Employe.actif.desc(), Employe.nom).all()
    return render_template("salaires/employes.html", employes=liste)


@salaires_bp.route("/employes/<int:employe_id>")
@role_required("salaires")
def employe_detail(employe_id):
    employe = db.get_or_404(Employe, employe_id)
    bulletins_recents = (
        Salaire.query.filter_by(employe_id=employe.id)
        .order_by(Salaire.annee.desc(), Salaire.mois.desc())
        .limit(12)
        .all()
    )
    return render_template(
        "salaires/employe_detail.html",
        employe=employe,
        bulletins=bulletins_recents,
        sexes=SEXES,
        mois_fr=MOIS_FR,
        statuts=STATUTS_SALAIRE,
    )


@salaires_bp.route("/employes/nouveau", methods=["GET", "POST"])
@role_required("salaires")
def employe_nouveau():
    if current_user.role == "admin":
        flash("Un compte admin ne peut pas ajouter d'employé directement.", "warning")
        return redirect(url_for("salaires.employes"))

    peut_gerer_compte = current_user.role == "admin"

    if request.method == "POST":
        erreurs = _valider_employe(request.form)
        compte_data = None
        if peut_gerer_compte:
            compte_erreurs, compte_data = _valider_compte(request.form)
            erreurs += compte_erreurs

        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "salaires/employe_form.html", employe=None, form=request.form,
                sexes=SEXES, types_contrat=TYPES_CONTRAT, modes_paiement=MODES_PAIEMENT,
                roles_compte=ROLES_COMPTE, peut_gerer_compte=peut_gerer_compte, compte=None,
            )

        employe = Employe(actif=True)
        _remplir_employe(employe, request.form)
        db.session.add(employe)
        db.session.flush()
        if not employe.matricule:
            employe.matricule = f"EMP-{employe.id:04d}"

        if compte_data:
            compte = User(
                nom=employe.nom,
                username=compte_data["username"],
                email=employe.email or None,
                role=compte_data["role"],
                employe_id=employe.id,
            )
            compte.set_password(compte_data["password"])
            db.session.add(compte)

        db.session.commit()
        flash("Employé ajouté avec succès.", "success")
        return redirect(url_for("salaires.employe_detail", employe_id=employe.id))

    return render_template(
        "salaires/employe_form.html", employe=None, form={},
        sexes=SEXES, types_contrat=TYPES_CONTRAT, modes_paiement=MODES_PAIEMENT,
        roles_compte=ROLES_COMPTE, peut_gerer_compte=peut_gerer_compte, compte=None,
    )


@salaires_bp.route("/employes/<int:employe_id>/modifier", methods=["GET", "POST"])
@role_required("salaires")
def employe_modifier(employe_id):
    employe = db.get_or_404(Employe, employe_id)
    peut_gerer_compte = current_user.role == "admin"
    compte_existant = employe.compte_utilisateur

    if request.method == "POST":
        erreurs = _valider_employe(request.form, employe_id=employe.id)
        compte_data = None
        if peut_gerer_compte:
            compte_erreurs, compte_data = _valider_compte(
                request.form, user_id=compte_existant.id if compte_existant else None
            )
            erreurs += compte_erreurs

        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template(
                "salaires/employe_form.html", employe=employe, form=request.form,
                sexes=SEXES, types_contrat=TYPES_CONTRAT, modes_paiement=MODES_PAIEMENT,
                roles_compte=ROLES_COMPTE, peut_gerer_compte=peut_gerer_compte, compte=compte_existant,
            )

        _remplir_employe(employe, request.form)

        if compte_data:
            if compte_existant:
                compte_existant.username = compte_data["username"]
                compte_existant.role = compte_data["role"]
                if compte_data["password"]:
                    compte_existant.set_password(compte_data["password"])
            else:
                compte = User(
                    nom=employe.nom,
                    username=compte_data["username"],
                    email=employe.email or None,
                    role=compte_data["role"],
                    employe_id=employe.id,
                )
                compte.set_password(compte_data["password"])
                db.session.add(compte)

        db.session.commit()
        flash("Employé modifié avec succès.", "success")
        return redirect(url_for("salaires.employe_detail", employe_id=employe.id))

    form = {
        "matricule": employe.matricule or "",
        "nom": employe.nom,
        "poste": employe.poste or "",
        "departement": employe.departement or "",
        "salaire_base": employe.salaire_base,
        "telephone": employe.telephone or "",
        "email": employe.email or "",
        "adresse": employe.adresse or "",
        "date_naissance": employe.date_naissance.isoformat() if employe.date_naissance else "",
        "sexe": employe.sexe or "",
        "numero_piece_identite": employe.numero_piece_identite or "",
        "date_embauche": employe.date_embauche.isoformat() if employe.date_embauche else "",
        "type_contrat": employe.type_contrat or "",
        "mode_paiement": employe.mode_paiement or "",
        "numero_compte": employe.numero_compte or "",
    }
    return render_template(
        "salaires/employe_form.html", employe=employe, form=form,
        sexes=SEXES, types_contrat=TYPES_CONTRAT, modes_paiement=MODES_PAIEMENT,
        roles_compte=ROLES_COMPTE, peut_gerer_compte=peut_gerer_compte, compte=compte_existant,
    )


@salaires_bp.route("/employes/<int:employe_id>/acces", methods=["GET", "POST"])
@admin_required
def employe_acces(employe_id):
    employe = db.get_or_404(Employe, employe_id)

    if request.method == "POST":
        if not employe.email:
            flash("L'employé doit avoir une adresse email avant de configurer son accès.", "danger")
            return redirect(url_for("salaires.employe_acces", employe_id=employe.id))

        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")

        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères.", "danger")
        elif password != confirmation:
            flash("Les mots de passe ne correspondent pas.", "danger")
        else:
            employe.set_password(password)
            db.session.commit()
            flash("Accès employé configuré avec succès.", "success")
            return redirect(url_for("salaires.employe_detail", employe_id=employe.id))

    historique = (
        ConnexionLog.query.filter_by(employe_id=employe.id)
        .order_by(ConnexionLog.date_heure.desc())
        .limit(50)
        .all()
    )
    return render_template("salaires/employe_acces.html", employe=employe, historique=historique)


@salaires_bp.route("/employes/<int:employe_id>/toggle-actif", methods=["POST"])
@role_required("salaires")
def employe_toggle_actif(employe_id):
    if current_user.role == "secretaire":
        flash("Un compte secrétaire ne peut pas activer/désactiver un employé.", "warning")
        return redirect(request.referrer or url_for("salaires.employes"))

    employe = db.get_or_404(Employe, employe_id)
    employe.actif = not employe.actif
    db.session.commit()
    flash(f"Employé {'réactivé' if employe.actif else 'désactivé'}.", "info")
    return redirect(request.referrer or url_for("salaires.employes"))


@salaires_bp.route("/employes/<int:employe_id>/supprimer", methods=["POST"])
@role_required("salaires")
def employe_supprimer(employe_id):
    employe = db.get_or_404(Employe, employe_id)
    if employe.bulletins:
        flash("Impossible de supprimer cet employé : des bulletins de salaire existent déjà. Désactivez-le à la place.", "danger")
        return redirect(url_for("salaires.employes"))

    db.session.delete(employe)
    db.session.commit()
    flash("Employé supprimé.", "info")
    return redirect(url_for("salaires.employes"))


def _remplir_employe(employe, form):
    employe.matricule = form.get("matricule", "").strip() or None
    employe.nom = form.get("nom", "").strip()
    employe.poste = form.get("poste", "").strip() or None
    employe.departement = form.get("departement", "").strip() or None
    employe.salaire_base = form.get("salaire_base")

    employe.telephone = form.get("telephone", "").strip() or None
    employe.email = form.get("email", "").strip() or None
    employe.adresse = form.get("adresse", "").strip() or None

    employe.date_naissance = _parse_date(form.get("date_naissance"))
    employe.sexe = form.get("sexe") or None
    employe.numero_piece_identite = form.get("numero_piece_identite", "").strip() or None

    employe.date_embauche = _parse_date(form.get("date_embauche"))
    employe.type_contrat = form.get("type_contrat") or None

    employe.mode_paiement = form.get("mode_paiement") or None
    employe.numero_compte = form.get("numero_compte", "").strip() or None


def _valider_employe(form, employe_id=None):
    erreurs = []
    if not form.get("nom", "").strip():
        erreurs.append("Le nom est obligatoire.")

    salaire_brut = form.get("salaire_base", "").strip()
    try:
        salaire = float(salaire_brut)
        if salaire <= 0:
            erreurs.append("Le salaire de base doit être supérieur à 0.")
    except (TypeError, ValueError):
        erreurs.append("Le salaire de base est invalide.")

    matricule = form.get("matricule", "").strip()
    if matricule:
        query = Employe.query.filter_by(matricule=matricule)
        if employe_id:
            query = query.filter(Employe.id != employe_id)
        if query.first():
            erreurs.append(f"Le matricule '{matricule}' est déjà utilisé par un autre employé.")

    email = form.get("email", "").strip()
    if email:
        query = Employe.query.filter(Employe.email.ilike(email))
        if employe_id:
            query = query.filter(Employe.id != employe_id)
        if query.first():
            erreurs.append(f"L'email '{email}' est déjà utilisé par un autre employé.")

    return erreurs


def _valider_compte(form, user_id=None):
    """Valide les champs du panneau 'Compte système'. Retourne (erreurs, donnees_ou_None).
    donnees_ou_None vaut None si aucun compte n'est demandé (champ username vide)."""
    username = form.get("compte_username", "").strip()
    if not username:
        return [], None

    erreurs = []

    role = form.get("compte_role", "")
    if role not in ROLES_COMPTE:
        erreurs.append("Le type de compte sélectionné est invalide.")

    query = User.query.filter(User.username.ilike(username))
    if user_id:
        query = query.filter(User.id != user_id)
    if query.first():
        erreurs.append(f"Le nom d'utilisateur '{username}' est déjà utilisé.")

    password = form.get("compte_password", "")
    confirmation = form.get("compte_password_confirmation", "")

    if not user_id or password or confirmation:
        if len(password) < 6:
            erreurs.append("Le mot de passe du compte système doit contenir au moins 6 caractères.")
        elif password != confirmation:
            erreurs.append("Les mots de passe du compte système ne correspondent pas.")

    return erreurs, {"username": username, "role": role, "password": password}


# --- Bulletins de salaire ----------------------------------------------

@salaires_bp.route("/")
@salaires_bp.route("/bulletins")
@role_required("salaires", "salaires_paiement")
def bulletins():
    today = date.today()
    annee = request.args.get("annee", today.year, type=int)
    mois = request.args.get("mois", today.month, type=int)

    liste = (
        Salaire.query.filter_by(annee=annee, mois=mois)
        .join(Employe)
        .order_by(Employe.nom)
        .all()
    )

    masse_salariale = sum(float(s.montant) for s in liste)
    nb_employes_actifs = Employe.query.filter_by(actif=True).count()

    return render_template(
        "salaires/bulletins.html",
        bulletins=liste,
        annee=annee,
        mois=mois,
        mois_fr=MOIS_FR,
        statuts=STATUTS_SALAIRE,
        masse_salariale=masse_salariale,
        nb_employes_actifs=nb_employes_actifs,
        annees=range(today.year - 2, today.year + 2),
    )


@salaires_bp.route("/bulletins/generer", methods=["POST"])
@role_required("salaires")
def bulletins_generer():
    annee = request.form.get("annee", type=int)
    mois = request.form.get("mois", type=int)

    if current_user.role == "admin":
        flash("Un compte admin ne peut pas générer les bulletins, seulement les valider.", "warning")
        return redirect(url_for("salaires.bulletins", annee=annee, mois=mois))

    employes_actifs = Employe.query.filter_by(actif=True).all()
    deja_existants = {
        (s.employe_id) for s in Salaire.query.filter_by(annee=annee, mois=mois).all()
    }

    crees = 0
    for employe in employes_actifs:
        if employe.id in deja_existants:
            continue
        jours_travailles, jours_absence = calculer_presence_mensuelle(employe.id, mois, annee)
        bulletin = Salaire(
            employe_id=employe.id,
            mois=mois,
            annee=annee,
            salaire_base=employe.salaire_base,
            primes=0,
            retenues=0,
            montant=employe.salaire_base,
            jours_travailles=jours_travailles,
            jours_absence=jours_absence,
            statut="en_attente",
        )
        db.session.add(bulletin)
        db.session.flush()
        bulletin.numero_bulletin = f"BUL-{annee}{mois:02d}-{bulletin.id:04d}"
        crees += 1

    db.session.commit()

    if crees:
        flash(f"{crees} bulletin(s) généré(s) pour la période sélectionnée.", "success")
    else:
        flash("Aucun nouveau bulletin à générer (déjà existants ou aucun employé actif).", "info")

    return redirect(url_for("salaires.bulletins", annee=annee, mois=mois))


@salaires_bp.route("/bulletins/<int:bulletin_id>")
@role_required("salaires", "salaires_paiement")
def bulletin_detail(bulletin_id):
    bulletin = db.get_or_404(Salaire, bulletin_id)

    historique_bulletins = (
        Salaire.query.filter_by(employe_id=bulletin.employe_id)
        .order_by(Salaire.annee.desc(), Salaire.mois.desc())
        .limit(12)
        .all()
    )
    stats_presence = statistiques_annuelles_employe(bulletin.employe_id, bulletin.annee)

    return render_template(
        "salaires/bulletin_detail.html", bulletin=bulletin, mois_fr=MOIS_FR, statuts=STATUTS_SALAIRE,
        now=datetime.now(), historique_bulletins=historique_bulletins, stats_presence=stats_presence,
    )


@salaires_bp.route("/bulletins/<int:bulletin_id>/modifier", methods=["GET", "POST"])
@role_required("salaires")
def bulletin_modifier(bulletin_id):
    bulletin = db.get_or_404(Salaire, bulletin_id)

    if bulletin.statut != "en_attente":
        flash("Ce bulletin est déjà validé ou payé, il ne peut plus être modifié.", "warning")
        return redirect(url_for("salaires.bulletin_detail", bulletin_id=bulletin.id))

    if request.method == "POST":
        erreurs, valeurs = _valider_bulletin(request.form)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
            return render_template("salaires/bulletin_form.html", bulletin=bulletin, statuts=STATUTS_SALAIRE, mois_fr=MOIS_FR)

        bulletin.salaire_base = valeurs["salaire_base"]
        bulletin.primes = valeurs["primes"]
        bulletin.primes_detail = request.form.get("primes_detail", "").strip() or None
        bulletin.retenues = valeurs["retenues"]
        bulletin.retenues_detail = request.form.get("retenues_detail", "").strip() or None
        bulletin.montant = valeurs["salaire_base"] + valeurs["primes"] - valeurs["retenues"]

        jours_travailles = request.form.get("jours_travailles", "").strip()
        bulletin.jours_travailles = int(jours_travailles) if jours_travailles else None
        jours_absence = request.form.get("jours_absence", "").strip()
        bulletin.jours_absence = int(jours_absence) if jours_absence else None
        bulletin.note = request.form.get("note", "").strip() or None

        db.session.commit()
        flash("Bulletin mis à jour.", "success")
        return redirect(url_for("salaires.bulletin_detail", bulletin_id=bulletin.id))

    return render_template("salaires/bulletin_form.html", bulletin=bulletin, statuts=STATUTS_SALAIRE, mois_fr=MOIS_FR)


def _valider_bulletin(form):
    erreurs = []
    valeurs = {}

    for champ, label in (("salaire_base", "Le salaire de base"), ("primes", "Les primes"), ("retenues", "Les retenues")):
        brut = form.get(champ, "0").strip() or "0"
        try:
            valeur = float(brut)
            if valeur < 0:
                erreurs.append(f"{label} ne peuvent pas être négatif(ve)s.")
            valeurs[champ] = valeur
        except (TypeError, ValueError):
            erreurs.append(f"{label} est invalide.")
            valeurs[champ] = 0

    if not erreurs and valeurs["salaire_base"] + valeurs["primes"] - valeurs["retenues"] <= 0:
        erreurs.append("Le net à payer (salaire + primes − retenues) doit être supérieur à 0.")

    return erreurs, valeurs


@salaires_bp.route("/bulletins/<int:bulletin_id>/valider", methods=["POST"])
@admin_required
def bulletin_valider(bulletin_id):
    bulletin = db.get_or_404(Salaire, bulletin_id)

    if bulletin.statut != "en_attente":
        flash("Ce bulletin n'est plus en attente de validation.", "info")
    else:
        bulletin.statut = "valide"
        db.session.commit()
        flash("Bulletin validé. Le RAF peut maintenant procéder au paiement.", "success")

    return redirect(request.referrer or url_for("salaires.bulletins"))


@salaires_bp.route("/bulletins/<int:bulletin_id>/paiement", methods=["GET", "POST"])
@role_required("salaires_paiement")
def bulletin_ajouter_paiement(bulletin_id):
    bulletin = db.get_or_404(Salaire, bulletin_id)

    if current_user.role != "comptable":
        flash("Seul un compte RAF peut finaliser le paiement d'un bulletin.", "warning")
        return redirect(url_for("salaires.bulletin_detail", bulletin_id=bulletin.id))

    if bulletin.statut != "valide":
        flash("Ce bulletin doit d'abord être validé par un administrateur.", "warning")
        return redirect(url_for("salaires.bulletin_detail", bulletin_id=bulletin.id))

    if request.method == "POST":
        mode_paiement = request.form.get("mode_paiement")
        if mode_paiement not in ("cash", "compte_bancaire"):
            flash("Le mode de paiement est invalide.", "danger")
            return redirect(url_for("salaires.bulletin_ajouter_paiement", bulletin_id=bulletin.id))

        bulletin.mode_paiement = mode_paiement
        bulletin.statut = "paye"
        bulletin.date_paiement = date.today()

        if mode_paiement == "compte_bancaire":
            libelle = request.form.get("libelle_bancaire", "").strip() or f"Salaire {bulletin.employe.nom} - {MOIS_FR[bulletin.mois - 1]} {bulletin.annee}"
            reference_paiement = request.form.get("reference_paiement", "").strip() or None
            bulletin.libelle_bancaire = libelle
            bulletin.reference_paiement = reference_paiement

            transaction = TransactionBancaire(
                date=bulletin.date_paiement,
                beneficiaire=bulletin.employe.nom,
                libelle=libelle,
                reference_paiement=reference_paiement,
                montant=bulletin.montant,
                sens="credit",
                valide=True,
                valide_le=datetime.now(),
            )
            db.session.add(transaction)
            db.session.flush()
            bulletin.transaction_bancaire_id = transaction.id
            flash("Bulletin payé par virement bancaire, transaction ajoutée au Compte Bancaire.", "success")
        else:
            flash("Bulletin marqué comme payé en cash.", "success")

        db.session.commit()
        return redirect(url_for("salaires.bulletin_detail", bulletin_id=bulletin.id))

    return render_template("salaires/bulletin_paiement.html", bulletin=bulletin, mois_fr=MOIS_FR)


@salaires_bp.route("/bulletins/<int:bulletin_id>/supprimer", methods=["POST"])
@role_required("salaires")
def bulletin_supprimer(bulletin_id):
    bulletin = db.get_or_404(Salaire, bulletin_id)

    if bulletin.statut != "en_attente":
        flash("Ce bulletin est déjà validé ou payé, il ne peut plus être supprimé.", "warning")
        return redirect(url_for("salaires.bulletin_detail", bulletin_id=bulletin.id))

    annee, mois = bulletin.annee, bulletin.mois
    db.session.delete(bulletin)
    db.session.commit()
    flash("Bulletin supprimé.", "info")
    return redirect(url_for("salaires.bulletins", annee=annee, mois=mois))
