from datetime import date, datetime, time, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import extract

from app import db
from app.models import SessionPresence, Presence, Employe, Salaire, HoraireProgramme, DemandeAbsence
from app.decorators import role_required, confirmation_presence_required, admin_required
from app.constants import MOIS_FR, MOTIFS_ABSENCE, STATUTS_DEMANDE_ABSENCE

presence_bp = Blueprint("presence", __name__, url_prefix="/presence")

MOIS_FR_ABREGE = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
    "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
]

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _employe_id_courant():
    """Retourne l'id Employe à utiliser pour la présence de l'utilisateur connecté
    (l'employé lui-même, ou l'employé lié pour un compte comptable/secrétaire)."""
    if current_user.is_admin_account:
        return current_user.employe_id
    return current_user.id


def _horaire_programme():
    horaire = HoraireProgramme.query.first()
    if not horaire:
        horaire = HoraireProgramme()
        db.session.add(horaire)
        db.session.commit()
    return horaire


def _auto_lancer_session_du_jour():
    """Crée automatiquement l'appel du jour à partir des horaires programmés,
    si le jour fait partie des jours actifs et qu'aucun appel n'existe déjà."""
    today = date.today()
    horaire = _horaire_programme()
    if today.weekday() not in horaire.jours_actifs_liste():
        return
    if SessionPresence.query.filter_by(date=today).first():
        return

    session = SessionPresence(
        date=today,
        heure_debut=horaire.heure_debut_entree,
        heure_fin=horaire.heure_fin_entree,
        heure_debut_sortie=horaire.heure_debut_sortie,
        heure_fin_sortie=horaire.heure_fin_sortie,
        statut="ouverte",
    )
    db.session.add(session)
    db.session.commit()


def _auto_close_expired_sessions():
    now = datetime.now()
    ouvertes = SessionPresence.query.filter_by(statut="ouverte").all()
    a_fermer = [
        s for s in ouvertes
        if now > datetime.combine(s.date, s.heure_fin_sortie or s.heure_fin)
    ]
    for session in a_fermer:
        session.statut = "fermee"
    if a_fermer:
        db.session.commit()
        for session in a_fermer:
            _synchroniser_bulletins(session.date.month, session.date.year)


def calculer_presence_mensuelle(employe_id, mois, annee):
    """Retourne (jours_travailles, jours_absence) à partir des sessions clôturées du mois."""
    _auto_close_expired_sessions()

    sessions_mois = SessionPresence.query.filter(
        SessionPresence.statut == "fermee",
        extract("year", SessionPresence.date) == annee,
        extract("month", SessionPresence.date) == mois,
    ).all()

    if not sessions_mois:
        return None, None

    session_ids = [s.id for s in sessions_mois]
    jours_travailles = Presence.query.filter(
        Presence.employe_id == employe_id,
        Presence.session_id.in_(session_ids),
        Presence.heure_sortie.isnot(None),
    ).count()
    jours_absence = len(sessions_mois) - jours_travailles
    return jours_travailles, jours_absence


def jours_absence_justifies(employe_id, mois, annee):
    """Parmi les jours d'absence du mois, combien sont couverts par une demande
    d'absence validée. Ne change pas le décompte jours_absence : sert juste à
    l'annoter (l'absence reste comptée, seulement documentée)."""
    sessions_mois = SessionPresence.query.filter(
        SessionPresence.statut == "fermee",
        extract("year", SessionPresence.date) == annee,
        extract("month", SessionPresence.date) == mois,
    ).all()
    if not sessions_mois:
        return 0

    session_ids = [s.id for s in sessions_mois]
    ids_sessions_travaillees = {
        p.session_id for p in Presence.query.filter(
            Presence.employe_id == employe_id,
            Presence.session_id.in_(session_ids),
            Presence.heure_sortie.isnot(None),
        ).all()
    }

    demandes_validees = DemandeAbsence.query.filter_by(employe_id=employe_id, statut="validee").all()
    if not demandes_validees:
        return 0

    justifiees = 0
    for session in sessions_mois:
        if session.id in ids_sessions_travaillees:
            continue
        if any(d.date_debut <= session.date <= d.date_fin for d in demandes_validees):
            justifiees += 1
    return justifiees


def statistiques_annuelles_employe(employe_id, annee):
    """Évolution mensuelle (jours travaillés/absence) et taux de présence sur l'année."""
    evolution = []
    total_travailles = 0
    total_absence = 0

    for mois in range(1, 13):
        jours_travailles, jours_absence = calculer_presence_mensuelle(employe_id, mois, annee)
        jours_travailles = jours_travailles or 0
        jours_absence = jours_absence or 0
        evolution.append({
            "label": MOIS_FR_ABREGE[mois - 1],
            "jours_travailles": jours_travailles,
            "jours_absence": jours_absence,
        })
        total_travailles += jours_travailles
        total_absence += jours_absence

    total_jours = total_travailles + total_absence
    taux_presence = round((total_travailles / total_jours) * 100, 1) if total_jours else None

    return {
        "evolution": evolution,
        "total_travailles": total_travailles,
        "total_absence": total_absence,
        "taux_presence": taux_presence,
    }


def _synchroniser_bulletins(mois, annee, employe_id=None):
    """Met à jour les jours travaillés/absence des bulletins déjà générés pour ce mois
    (uniquement ceux non encore payés, qui restent modifiables)."""
    query = Salaire.query.filter_by(mois=mois, annee=annee, statut="en_attente")
    if employe_id is not None:
        query = query.filter_by(employe_id=employe_id)

    for bulletin in query.all():
        jours_travailles, jours_absence = calculer_presence_mensuelle(bulletin.employe_id, mois, annee)
        if jours_travailles is not None:
            bulletin.jours_travailles = jours_travailles
            bulletin.jours_absence = jours_absence

    db.session.commit()


@presence_bp.before_request
def _avant_chaque_requete():
    _auto_lancer_session_du_jour()
    _auto_close_expired_sessions()


# --- Espace admin -------------------------------------------------------

@presence_bp.route("/")
@role_required("presence")
def index():
    sessions = SessionPresence.query.order_by(SessionPresence.date.desc()).limit(30).all()
    nb_employes_actifs = Employe.query.filter_by(actif=True).count()

    resume = {}
    for session in sessions:
        nb_entrees = len(session.presences)
        nb_sorties = sum(1 for p in session.presences if p.heure_sortie)
        resume[session.id] = {
            "entrees": nb_entrees,
            "sorties": nb_sorties,
            "absents": max(nb_employes_actifs - nb_entrees, 0),
        }

    horaire = _horaire_programme()
    maintenant = datetime.now()
    if date.today().weekday() in horaire.jours_actifs_liste():
        heure_debut_defaut = horaire.heure_debut_entree.strftime("%H:%M")
        heure_fin_defaut = horaire.heure_fin_entree.strftime("%H:%M")
    else:
        heure_debut_defaut = maintenant.strftime("%H:%M")
        heure_fin_defaut = (maintenant + timedelta(minutes=30)).strftime("%H:%M")

    mois_actuel = date.today().month
    annee_actuelle = date.today().year
    employes_actifs = Employe.query.filter_by(actif=True).order_by(Employe.nom).all()
    situation_presence = []
    for employe in employes_actifs:
        jours_travailles, jours_absence = calculer_presence_mensuelle(employe.id, mois_actuel, annee_actuelle)
        jours_travailles = jours_travailles or 0
        jours_absence = jours_absence or 0
        total = jours_travailles + jours_absence
        situation_presence.append({
            "employe": employe,
            "jours_travailles": jours_travailles,
            "jours_absence": jours_absence,
            "jours_absence_justifies": jours_absence_justifies(employe.id, mois_actuel, annee_actuelle),
            "taux": round(jours_travailles / total * 100, 1) if total else None,
        })

    nb_jours_ouvres_mois = SessionPresence.query.filter(
        SessionPresence.statut == "fermee",
        extract("year", SessionPresence.date) == annee_actuelle,
        extract("month", SessionPresence.date) == mois_actuel,
    ).count()
    taux_connus = [l["taux"] for l in situation_presence if l["taux"] is not None]
    taux_moyen = round(sum(taux_connus) / len(taux_connus), 1) if taux_connus else None
    nb_demandes_en_attente = DemandeAbsence.query.filter_by(statut="en_attente").count()

    return render_template(
        "presence/index.html",
        sessions=sessions,
        resume=resume,
        nb_employes_actifs=nb_employes_actifs,
        today=date.today(),
        heure_debut_defaut=heure_debut_defaut,
        heure_fin_defaut=heure_fin_defaut,
        nb_jours_ouvres_mois=nb_jours_ouvres_mois,
        taux_moyen=taux_moyen,
        now=maintenant,
        horaire=horaire,
        jours_semaine=JOURS_SEMAINE,
        situation_presence=situation_presence,
        mois_label=f"{MOIS_FR[mois_actuel - 1]} {annee_actuelle}",
        nb_demandes_en_attente=nb_demandes_en_attente,
    )


@presence_bp.route("/horaire", methods=["POST"])
@role_required("presence")
def sauvegarder_horaire():
    try:
        debut_entree = time.fromisoformat(request.form.get("heure_debut_entree"))
        fin_entree = time.fromisoformat(request.form.get("heure_fin_entree"))
        debut_sortie = time.fromisoformat(request.form.get("heure_debut_sortie"))
        fin_sortie = time.fromisoformat(request.form.get("heure_fin_sortie"))
    except (TypeError, ValueError):
        flash("Heures invalides.", "danger")
        return redirect(url_for("presence.index"))

    if fin_entree <= debut_entree:
        flash("L'heure de fin d'entrée doit être après l'heure de début.", "danger")
        return redirect(url_for("presence.index"))

    if fin_sortie <= debut_sortie:
        flash("L'heure de fin de sortie doit être après l'heure de début.", "danger")
        return redirect(url_for("presence.index"))

    jours = request.form.getlist("jours_actifs")
    jours_valides = sorted({j for j in jours if j.isdigit() and 0 <= int(j) <= 6}, key=int)

    horaire = _horaire_programme()
    horaire.heure_debut_entree = debut_entree
    horaire.heure_fin_entree = fin_entree
    horaire.heure_debut_sortie = debut_sortie
    horaire.heure_fin_sortie = fin_sortie
    horaire.jours_actifs = ",".join(jours_valides)
    db.session.commit()

    # Répercute les nouveaux horaires sur l'appel du jour, chaque fenêtre restant
    # modifiable tant que personne ne l'a encore utilisée (entrée / sortie séparément).
    session_du_jour = SessionPresence.query.filter_by(date=date.today()).first()
    if session_du_jour:
        maj = False
        if not session_du_jour.presences:
            session_du_jour.heure_debut = debut_entree
            session_du_jour.heure_fin = fin_entree
            maj = True
        if not any(p.heure_sortie for p in session_du_jour.presences):
            session_du_jour.heure_debut_sortie = debut_sortie
            session_du_jour.heure_fin_sortie = fin_sortie
            maj = True
        if maj:
            db.session.commit()

    flash("Horaires programmés enregistrés.", "success")
    return redirect(url_for("presence.index"))


@presence_bp.route("/lancer", methods=["POST"])
@role_required("presence")
def lancer():
    date_session = request.form.get("date")
    heure_debut = request.form.get("heure_debut")
    heure_fin = request.form.get("heure_fin")

    try:
        date_valeur = date.fromisoformat(date_session)
        debut_valeur = time.fromisoformat(heure_debut)
        fin_valeur = time.fromisoformat(heure_fin)
    except (TypeError, ValueError):
        flash("Date ou heures invalides.", "danger")
        return redirect(url_for("presence.index"))

    if fin_valeur <= debut_valeur:
        flash("L'heure de fin doit être après l'heure de début.", "danger")
        return redirect(url_for("presence.index"))

    if SessionPresence.query.filter_by(date=date_valeur).first():
        flash(f"Un appel existe déjà pour le {date_valeur.strftime('%d/%m/%Y')}.", "danger")
        return redirect(url_for("presence.index"))

    horaire = _horaire_programme()
    session = SessionPresence(
        date=date_valeur, heure_debut=debut_valeur, heure_fin=fin_valeur,
        heure_debut_sortie=horaire.heure_debut_sortie, heure_fin_sortie=horaire.heure_fin_sortie,
        statut="ouverte",
    )
    db.session.add(session)
    db.session.commit()
    flash(f"Appel lancé pour le {date_valeur.strftime('%d/%m/%Y')}.", "success")
    return redirect(url_for("presence.detail", session_id=session.id))


@presence_bp.route("/<int:session_id>")
@role_required("presence")
def detail(session_id):
    session = db.get_or_404(SessionPresence, session_id)

    employes_actifs = Employe.query.filter_by(actif=True).order_by(Employe.nom).all()
    confirmations = {p.employe_id: p for p in session.presences}

    lignes = []
    for employe in employes_actifs:
        presence = confirmations.get(employe.id)
        lignes.append({
            "employe": employe,
            "present": presence is not None,
            "heure_entree": presence.confirme_le if presence else None,
            "heure_sortie": presence.heure_sortie if presence else None,
        })

    return render_template("presence/detail.html", session=session, lignes=lignes)


@presence_bp.route("/<int:session_id>/cloturer", methods=["POST"])
@role_required("presence")
def cloturer(session_id):
    session = db.get_or_404(SessionPresence, session_id)
    session.statut = "fermee"
    db.session.commit()
    _synchroniser_bulletins(session.date.month, session.date.year)
    flash("Appel clôturé. Les employés n'ayant pas confirmé sont comptés absents.", "info")
    return redirect(url_for("presence.detail", session_id=session.id))


@presence_bp.route("/<int:session_id>/supprimer", methods=["POST"])
@role_required("presence")
def supprimer(session_id):
    session = db.get_or_404(SessionPresence, session_id)
    db.session.delete(session)
    db.session.commit()
    flash("Appel supprimé.", "info")
    return redirect(url_for("presence.index"))


# --- Confirmation de présence (employés + comptes comptable/secrétaire) ----

@presence_bp.route("/confirmer", methods=["GET", "POST"])
@confirmation_presence_required
def confirmer():
    employe_id = _employe_id_courant()
    if employe_id is None:
        flash(
            "Votre compte n'est pas lié à une fiche employé, la présence ne peut pas être "
            "enregistrée. Contactez un administrateur (Salaires → Employés → Accès).",
            "warning",
        )
        return redirect(url_for("dashboard.index"))

    today = date.today()
    session = SessionPresence.query.filter_by(date=today).first()

    presence = None
    if session:
        presence = Presence.query.filter_by(session_id=session.id, employe_id=employe_id).first()

    entree_faite = presence is not None
    sortie_faite = bool(presence and presence.heure_sortie)

    def _fenetre(debut, fin, reference):
        return bool(session and debut and fin and datetime.combine(session.date, debut) <= reference <= datetime.combine(session.date, fin))

    if request.method == "POST":
        now = datetime.now()
        action = request.form.get("action")
        if not session:
            flash("Aucun appel n'est ouvert aujourd'hui.", "warning")
        elif action == "entree":
            if entree_faite:
                flash("Votre entrée est déjà enregistrée.", "info")
            elif not _fenetre(session.heure_debut, session.heure_fin, now):
                flash("La fenêtre de confirmation de l'entrée n'est pas active.", "danger")
            else:
                db.session.add(Presence(session_id=session.id, employe_id=employe_id, confirme_le=now))
                db.session.commit()
                _synchroniser_bulletins(session.date.month, session.date.year, employe_id=employe_id)
                flash("Entrée enregistrée. Bonne journée !", "success")
        elif action == "sortie":
            if not entree_faite:
                flash("Vous devez d'abord marquer votre entrée.", "warning")
            elif sortie_faite:
                flash("Votre sortie est déjà enregistrée.", "info")
            elif not _fenetre(session.heure_debut_sortie, session.heure_fin_sortie, now):
                flash("La fenêtre de confirmation de la sortie n'est pas active.", "danger")
            else:
                presence.heure_sortie = now
                db.session.commit()
                _synchroniser_bulletins(session.date.month, session.date.year, employe_id=employe_id)
                flash("Sortie enregistrée. Bonne fin de journée !", "success")
        return redirect(url_for("presence.confirmer"))

    now = datetime.now()
    fenetre_entree_ouverte = _fenetre(session.heure_debut, session.heure_fin, now) if session else False
    fenetre_sortie_ouverte = _fenetre(session.heure_debut_sortie, session.heure_fin_sortie, now) if session else False
    entree_expiree = bool(session and not entree_faite and now > datetime.combine(session.date, session.heure_fin))
    sortie_a_venir = bool(session and session.heure_debut_sortie and now < datetime.combine(session.date, session.heure_debut_sortie))
    sortie_expiree = bool(
        session and not sortie_faite and session.heure_fin_sortie
        and now > datetime.combine(session.date, session.heure_fin_sortie)
    )

    stats = statistiques_annuelles_employe(employe_id, today.year)

    return render_template(
        "presence/confirmer.html", session=session, entree_faite=entree_faite, sortie_faite=sortie_faite,
        presence=presence, fenetre_entree_ouverte=fenetre_entree_ouverte, fenetre_sortie_ouverte=fenetre_sortie_ouverte,
        entree_expiree=entree_expiree, sortie_a_venir=sortie_a_venir, sortie_expiree=sortie_expiree,
        now=now, annee=today.year, stats=stats,
    )


# --- Demandes d'absence (congé / justificatif) ---------------------------

@presence_bp.route("/mes-demandes", methods=["GET", "POST"])
@confirmation_presence_required
def mes_demandes():
    employe_id = _employe_id_courant()
    if employe_id is None:
        flash(
            "Votre compte n'est pas lié à une fiche employé, impossible de soumettre une "
            "demande. Contactez un administrateur (Salaires → Employés → Accès).",
            "warning",
        )
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        date_debut = date.fromisoformat(request.form.get("date_debut")) if request.form.get("date_debut") else None
        date_fin = date.fromisoformat(request.form.get("date_fin")) if request.form.get("date_fin") else None
        motif = request.form.get("motif")
        precision = request.form.get("precision", "").strip()

        erreurs = []
        if not date_debut or not date_fin:
            erreurs.append("Les dates de début et de fin sont obligatoires.")
        elif date_fin < date_debut:
            erreurs.append("La date de fin doit être après la date de début.")
        if motif not in MOTIFS_ABSENCE:
            erreurs.append("Le motif sélectionné est invalide.")
        elif motif == "autre" and not precision:
            erreurs.append("Merci de préciser le motif.")

        if erreurs:
            for erreur in erreurs:
                flash(erreur, "danger")
        else:
            db.session.add(DemandeAbsence(
                employe_id=employe_id, date_debut=date_debut, date_fin=date_fin,
                motif=motif, precision=precision or None,
            ))
            db.session.commit()
            flash("Demande envoyée, en attente de validation par un administrateur.", "success")
        return redirect(url_for("presence.mes_demandes"))

    demandes = DemandeAbsence.query.filter_by(employe_id=employe_id).order_by(
        DemandeAbsence.date_debut.desc()
    ).all()
    return render_template(
        "presence/mes_demandes.html", demandes=demandes,
        motifs=MOTIFS_ABSENCE, statuts=STATUTS_DEMANDE_ABSENCE, today=date.today(),
    )


@presence_bp.route("/demandes")
@role_required("presence")
def demandes():
    statut = request.args.get("statut", "")
    query = DemandeAbsence.query.join(Employe)
    if statut in STATUTS_DEMANDE_ABSENCE:
        query = query.filter(DemandeAbsence.statut == statut)
    liste_demandes = query.order_by(DemandeAbsence.created_at.desc()).all()

    return render_template(
        "presence/demandes.html", demandes=liste_demandes,
        motifs=MOTIFS_ABSENCE, statuts=STATUTS_DEMANDE_ABSENCE, statut_filtre=statut,
    )


@presence_bp.route("/demandes/<int:demande_id>/valider", methods=["POST"])
@admin_required
def demande_valider(demande_id):
    demande = db.get_or_404(DemandeAbsence, demande_id)
    demande.statut = "validee"
    demande.commentaire_admin = None
    demande.traite_le = datetime.now()
    db.session.commit()
    flash("Demande validée. L'absence reste comptée, mais est maintenant justifiée.", "success")
    return redirect(url_for("presence.demandes"))


@presence_bp.route("/demandes/<int:demande_id>/refuser", methods=["POST"])
@admin_required
def demande_refuser(demande_id):
    demande = db.get_or_404(DemandeAbsence, demande_id)
    demande.statut = "refusee"
    demande.commentaire_admin = request.form.get("commentaire_admin", "").strip() or None
    demande.traite_le = datetime.now()
    db.session.commit()
    flash("Demande refusée.", "info")
    return redirect(url_for("presence.demandes"))
