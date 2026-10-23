from datetime import datetime, time

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    is_admin_account = True

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="admin")
    employe_id = db.Column(db.Integer, db.ForeignKey("employes.id"), nullable=True)
    telephone = db.Column(db.String(30))
    adresse = db.Column(db.String(255))
    date_naissance = db.Column(db.Date)
    sexe = db.Column(db.String(1))
    numero_piece_identite = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employe = db.relationship("Employe", backref=db.backref("compte_utilisateur", uselist=False))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"user:{self.id}"

    def __repr__(self):
        return f"<User {self.email}>"


class Fournisseur(db.Model):
    __tablename__ = "fournisseurs"

    id = db.Column(db.Integer, primary_key=True)
    nom_societe = db.Column(db.String(150), nullable=False)
    numero_marche = db.Column(db.String(100))
    date_signature = db.Column(db.Date)
    montant_marche = db.Column(db.Numeric(14, 2))
    montant_acompte_initial = db.Column(db.Numeric(14, 2))
    date_facture_initiale = db.Column(db.Date)
    date_versement_initial = db.Column(db.Date)
    taux_garantie = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    garantie_livree_le = db.Column(db.Date)
    actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Coordonnées bancaires du fournisseur, pour générer l'ordre de virement.
    banque_nom = db.Column(db.String(150))
    compte_nom = db.Column(db.String(150))
    compte_numero = db.Column(db.String(100))
    code_swift = db.Column(db.String(30))

    @property
    def montant_acompte(self):
        """Total cumulé versé au fournisseur : acompte initial + montant net payé de toutes ses factures."""
        if self.montant_acompte_initial is None and not self.factures:
            return None
        base = float(self.montant_acompte_initial) if self.montant_acompte_initial else 0.0
        return base + sum(float(f.montant_net_paye) for f in self.factures)

    @property
    def date_versement(self):
        """Date du dernier versement effectué (acompte initial ou dernière facture payée)."""
        dates = [self.date_versement_initial] if self.date_versement_initial else []
        dates += [f.date_paiement or f.date_facture for f in self.factures if (f.date_paiement or f.date_facture)]
        return max(dates) if dates else None

    @property
    def taux_acompte(self):
        """Taux de l'acompte cumulé rapporté au montant du marché (grandit avec chaque facture payée),
        atteint 100% une fois la garantie de bonne exécution livrée."""
        if self.garantie_livree_le:
            return 100.0
        montant = self.montant_acompte
        if not self.montant_marche or montant is None:
            return None
        return round(montant / float(self.montant_marche) * 100, 2)

    def __repr__(self):
        return f"<Fournisseur {self.nom_societe}>"


class FactureFournisseur(db.Model):
    __tablename__ = "factures_fournisseur"

    id = db.Column(db.Integer, primary_key=True)
    fournisseur_id = db.Column(db.Integer, db.ForeignKey("fournisseurs.id"), nullable=False)
    reference = db.Column(db.String(100))
    date_facture = db.Column(db.Date, nullable=False)
    date_paiement = db.Column(db.Date)
    montant_net_paye = db.Column(db.Numeric(14, 2), nullable=False)
    valide = db.Column(db.Boolean, default=False, nullable=False)
    valide_le = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Renseignés lors de la génération de l'ordre de virement correspondant.
    numero_lettre = db.Column(db.String(50))
    description_paiement = db.Column(db.Text)

    fournisseur = db.relationship("Fournisseur", backref=db.backref(
        "factures", lazy=True, cascade="all, delete-orphan", order_by="FactureFournisseur.date_facture"
    ))


class ConfigOrdreVirement(db.Model):
    """Configuration unique (singleton) des informations fixes de l'ordre de virement :
    compte à débiter de la société, et signataire « Conseil de surveillance »."""

    __tablename__ = "config_ordre_virement"

    id = db.Column(db.Integer, primary_key=True)
    compte_source_intitule = db.Column(db.String(200), default="CONSTRUCTION DES VILLAS DES JEUX DES ILES")
    compte_source_numero = db.Column(db.String(50), default="9357")
    titre_signataire_conseil = db.Column(db.String(150), default="Le Président de l'UCCIA")
    nom_signataire_conseil = db.Column(db.String(150), default="M Chamsouddine AHMED")


class Depense(db.Model):
    __tablename__ = "depenses"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    montant = db.Column(db.Numeric(12, 2), nullable=False)
    categorie = db.Column(db.String(100))
    beneficiaire = db.Column(db.String(150))
    description = db.Column(db.String(255))
    mode_paiement = db.Column(db.String(20), nullable=False, default="cash")  # "cash" ou "compte_bancaire"
    libelle_bancaire = db.Column(db.String(255))
    reference_paiement = db.Column(db.String(100))
    transaction_bancaire_id = db.Column(db.Integer, db.ForeignKey("transactions_bancaires.id"))
    valide = db.Column(db.Boolean, default=False, nullable=False)
    valide_le = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Renseignés uniquement pour une dépense de catégorie "Carburant" : alimentent
    # automatiquement le suivi en litres (achat) de l'onglet Carburant.
    type_gaz = db.Column(db.String(10))  # "essence" ou "diesel"
    quantite_litres = db.Column(db.Numeric(10, 2))

    transaction_bancaire = db.relationship("TransactionBancaire")


class PlanComptable(db.Model):
    """Chart of accounts: mapping numéro comptable ↔ catégorie de dépense."""

    __tablename__ = "plan_comptable"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), nullable=False, unique=True)
    nom = db.Column(db.String(150), nullable=False)
    budget = db.Column(db.Numeric(14, 2))  # plafond max pour cette catégorie, optionnel
    actif = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<PlanComptable {self.numero} {self.nom}>"


class ConfigBudgetDepenses(db.Model):
    """Configuration unique (singleton) du budget global des dépenses de l'entreprise
    (hors marchés fournisseurs, suivis séparément)."""

    __tablename__ = "config_budget_depenses"

    id = db.Column(db.Integer, primary_key=True)
    montant = db.Column(db.Numeric(14, 2), nullable=False, default=0)


class CompteBancaireConfig(db.Model):
    """Configuration unique (singleton) du compte bancaire : solde avant la première transaction suivie."""

    __tablename__ = "compte_bancaire_config"

    id = db.Column(db.Integer, primary_key=True)
    solde_initial = db.Column(db.Numeric(14, 2), nullable=False, default=0)


class AppState(db.Model):
    """Ligne unique (singleton) : horodatage de la dernière écriture en base, utilisé
    par les pages pour détecter qu'il faut se rafraîchir (mise à jour quasi temps réel)."""

    __tablename__ = "app_state"

    id = db.Column(db.Integer, primary_key=True)
    last_modified_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class TransactionBancaire(db.Model):
    __tablename__ = "transactions_bancaires"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    beneficiaire = db.Column(db.String(150))
    libelle = db.Column(db.String(255))
    reference_paiement = db.Column(db.String(100))
    montant = db.Column(db.Numeric(14, 2), nullable=False)
    sens = db.Column(db.String(10), nullable=False)  # "debit" (entrée) ou "credit" (sortie)
    valide = db.Column(db.Boolean, default=False, nullable=False)
    valide_le = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Employe(UserMixin, db.Model):
    __tablename__ = "employes"

    is_admin_account = False

    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(30), unique=True)
    nom = db.Column(db.String(150), nullable=False)
    poste = db.Column(db.String(120))
    departement = db.Column(db.String(100))
    salaire_base = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    actif = db.Column(db.Boolean, default=True)

    # Coordonnées
    telephone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    adresse = db.Column(db.String(255))

    # Identité civile
    date_naissance = db.Column(db.Date)
    sexe = db.Column(db.String(1))
    numero_piece_identite = db.Column(db.String(50))

    # Contrat de travail
    date_embauche = db.Column(db.Date)
    type_contrat = db.Column(db.String(30))

    # Informations de paiement
    mode_paiement = db.Column(db.String(30))
    numero_compte = db.Column(db.String(50))

    # Accès à l'espace employé
    password_hash = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bulletins = db.relationship("Salaire", backref="employe", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"employe:{self.id}"

    def __repr__(self):
        return f"<Employe {self.nom}>"


class Salaire(db.Model):
    __tablename__ = "salaires"

    id = db.Column(db.Integer, primary_key=True)
    numero_bulletin = db.Column(db.String(30), unique=True)
    employe_id = db.Column(db.Integer, db.ForeignKey("employes.id"), nullable=False)
    mois = db.Column(db.Integer, nullable=False)
    annee = db.Column(db.Integer, nullable=False)

    salaire_base = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    primes = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    primes_detail = db.Column(db.String(255))
    retenues = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    retenues_detail = db.Column(db.String(255))
    montant = db.Column(db.Numeric(12, 2), nullable=False)

    jours_travailles = db.Column(db.Integer)
    jours_absence = db.Column(db.Integer)
    motif_absence = db.Column(db.String(30))
    note = db.Column(db.Text)

    date_paiement = db.Column(db.Date, nullable=True)
    statut = db.Column(db.String(20), nullable=False, default="en_attente")
    mode_paiement = db.Column(db.String(20))  # "cash" ou "compte_bancaire", défini par le comptable
    libelle_bancaire = db.Column(db.String(255))
    reference_paiement = db.Column(db.String(100))
    transaction_bancaire_id = db.Column(db.Integer, db.ForeignKey("transactions_bancaires.id"))
    depense_id = db.Column(db.Integer, db.ForeignKey("depenses.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transaction_bancaire = db.relationship("TransactionBancaire")
    depense = db.relationship("Depense")

    __table_args__ = (
        db.UniqueConstraint("employe_id", "mois", "annee", name="uq_salaire_employe_mois_annee"),
    )


class HoraireProgramme(db.Model):
    """Configuration unique (singleton) des horaires par défaut de l'appel quotidien."""

    __tablename__ = "horaire_programme"

    id = db.Column(db.Integer, primary_key=True)
    heure_debut_entree = db.Column(db.Time, nullable=False, default=time(8, 0))
    heure_fin_entree = db.Column(db.Time, nullable=False, default=time(8, 30))
    heure_debut_sortie = db.Column(db.Time, nullable=False, default=time(17, 0))
    heure_fin_sortie = db.Column(db.Time, nullable=False, default=time(17, 30))
    jours_actifs = db.Column(db.String(20), nullable=False, default="0,1,2,3,4")

    def jours_actifs_liste(self):
        return [int(j) for j in self.jours_actifs.split(",") if j != ""]


class SessionPresence(db.Model):
    __tablename__ = "sessions_presence"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    heure_debut = db.Column(db.Time, nullable=False)
    heure_fin = db.Column(db.Time, nullable=False)
    heure_debut_sortie = db.Column(db.Time)
    heure_fin_sortie = db.Column(db.Time)
    statut = db.Column(db.String(20), nullable=False, default="ouverte")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    presences = db.relationship("Presence", backref="session", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SessionPresence {self.date}>"


class Presence(db.Model):
    __tablename__ = "presences"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions_presence.id"), nullable=False)
    employe_id = db.Column(db.Integer, db.ForeignKey("employes.id"), nullable=False)
    confirme_le = db.Column(db.DateTime, default=datetime.now)
    heure_sortie = db.Column(db.DateTime)

    employe = db.relationship("Employe", backref="presences", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("session_id", "employe_id", name="uq_presence_session_employe"),
    )


class DemandeAbsence(db.Model):
    """Demande de congé ou justificatif d'absence (maladie, empêchement, autre).
    Validée ou non, elle ne change pas le décompte jours travaillés/absence : elle
    sert uniquement à documenter la raison d'une absence déjà enregistrée."""

    __tablename__ = "demandes_absence"

    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(db.Integer, db.ForeignKey("employes.id"), nullable=False)
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date, nullable=False)
    motif = db.Column(db.String(20), nullable=False)
    precision = db.Column(db.Text)
    statut = db.Column(db.String(20), nullable=False, default="en_attente")
    commentaire_admin = db.Column(db.Text)
    traite_le = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employe = db.relationship("Employe", backref=db.backref("demandes_absence", lazy=True))


class AbsenceAutorisee(db.Model):
    """Absence autorisée ponctuelle (ex. sortie anticipée, arrivée tardive) sur un jour
    précis, avec l'heure concernée et le motif. Ajoutée directement par l'admin (déjà
    validée), ou demandée par l'employé puis validée/refusée par l'admin."""

    __tablename__ = "absences_autorisees"

    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(db.Integer, db.ForeignKey("employes.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    heure = db.Column(db.Time, nullable=False)
    motif = db.Column(db.Text, nullable=False)
    statut = db.Column(db.String(20), nullable=False, default="en_attente")
    traite_le = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employe = db.relationship("Employe", backref=db.backref("absences_autorisees", lazy=True))


class ConnexionLog(db.Model):
    __tablename__ = "connexions_log"

    id = db.Column(db.Integer, primary_key=True)
    employe_id = db.Column(db.Integer, db.ForeignKey("employes.id"), nullable=False)
    type_evenement = db.Column(db.String(10), nullable=False)  # 'login' ou 'logout'
    date_heure = db.Column(db.DateTime, default=datetime.now, nullable=False)
    adresse_ip = db.Column(db.String(45))

    employe = db.relationship("Employe", backref=db.backref(
        "connexions", lazy=True, order_by="ConnexionLog.date_heure.desc()"
    ))


class Appareil(db.Model):
    __tablename__ = "appareils"

    id = db.Column(db.Integer, primary_key=True)
    type_appareil = db.Column(db.String(50), nullable=False)
    marque = db.Column(db.String(100))
    modele = db.Column(db.String(100))
    numero_serie = db.Column(db.String(100))
    prix = db.Column(db.Numeric(12, 2))
    employe_id = db.Column(db.Integer, db.ForeignKey("employes.id"), nullable=True)
    statut = db.Column(db.String(20), nullable=False, default="en_service")
    date_attribution = db.Column(db.Date)
    notes = db.Column(db.Text)
    remplace_par_id = db.Column(db.Integer, db.ForeignKey("appareils.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    employe = db.relationship("Employe", backref="appareils", foreign_keys=[employe_id])
    remplace_par = db.relationship("Appareil", remote_side=[id], backref="remplace")

    def __repr__(self):
        return f"<Appareil {self.type_appareil} {self.marque or ''}>"


class DemandeAppareil(db.Model):
    __tablename__ = "demandes_appareil"

    id = db.Column(db.Integer, primary_key=True)
    appareil_id = db.Column(db.Integer, db.ForeignKey("appareils.id"), nullable=False)
    description = db.Column(db.Text, nullable=False)
    statut = db.Column(db.String(20), nullable=False, default="en_attente")
    date_demande = db.Column(db.DateTime, default=datetime.now)
    date_traitement = db.Column(db.DateTime)

    appareil = db.relationship("Appareil", backref=db.backref(
        "demandes", lazy=True, order_by="DemandeAppareil.date_demande.desc()"
    ))


class HistoriqueAppareil(db.Model):
    __tablename__ = "historique_appareil"

    id = db.Column(db.Integer, primary_key=True)
    appareil_id = db.Column(db.Integer, db.ForeignKey("appareils.id"), nullable=False)
    type_evenement = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text)
    date_evenement = db.Column(db.DateTime, default=datetime.now, nullable=False)

    appareil = db.relationship("Appareil", backref=db.backref(
        "historique", lazy=True, order_by="HistoriqueAppareil.date_evenement.desc()"
    ))


class Consommable(db.Model):
    __tablename__ = "consommables"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Consommable {self.nom}>"


class SuiviConsommable(db.Model):
    __tablename__ = "suivi_consommables"

    id = db.Column(db.Integer, primary_key=True)
    consommable_id = db.Column(db.Integer, db.ForeignKey("consommables.id"), nullable=False)
    mois = db.Column(db.Integer, nullable=False)
    annee = db.Column(db.Integer, nullable=False)
    montant = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    paye = db.Column(db.Boolean, default=False, nullable=False)
    date_paiement = db.Column(db.Date)
    notes = db.Column(db.Text)
    valide = db.Column(db.Boolean, default=False, nullable=False)
    valide_le = db.Column(db.DateTime)

    consommable = db.relationship("Consommable", backref=db.backref("suivis", lazy=True))

    __table_args__ = (
        db.UniqueConstraint("consommable_id", "mois", "annee", name="uq_suivi_consommable_mois_annee"),
    )


class ConfigCarburant(db.Model):
    """Configuration unique (singleton) du suivi des tickets de carburant."""

    __tablename__ = "config_carburant"

    id = db.Column(db.Integer, primary_key=True)
    seuil_alerte = db.Column(db.Integer, nullable=False, default=10)


class MouvementCarburant(db.Model):
    """Réception (achat de tickets) ou utilisation de tickets de carburant."""

    __tablename__ = "mouvements_carburant"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.now)
    type_mouvement = db.Column(db.String(15), nullable=False)  # "reception" ou "utilisation"
    quantite = db.Column(db.Integer, nullable=False)
    beneficiaire = db.Column(db.String(150))
    notes = db.Column(db.Text)
    type_gaz = db.Column(db.String(10))  # "essence" ou "diesel", pour une réception chiffrée
    quantite_litres = db.Column(db.Numeric(10, 2))
    montant = db.Column(db.Numeric(12, 2))  # quantite_litres × prix au litre, reflété dans le Suivi mensuel
    enregistre_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    enregistre_par = db.relationship("User")


class MouvementLitresCarburant(db.Model):
    """Suivi du carburant en litres (achat/utilisation), séparé du suivi en tickets.
    Un achat est créé automatiquement quand le RAF ajoute une dépense de catégorie
    « Carburant » (montant et litres saisis sur la dépense) ; une utilisation est
    enregistrée manuellement depuis l'onglet Carburant."""

    __tablename__ = "mouvements_litres_carburant"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.now)
    type_mouvement = db.Column(db.String(15), nullable=False)  # "achat" ou "utilisation"
    type_gaz = db.Column(db.String(10), nullable=False)  # "essence" ou "diesel"
    quantite_litres = db.Column(db.Numeric(10, 2), nullable=False)
    montant = db.Column(db.Numeric(12, 2))  # pour un achat, repris de la dépense liée
    depense_id = db.Column(db.Integer, db.ForeignKey("depenses.id"))
    beneficiaire = db.Column(db.String(150))  # véhicule, pour une utilisation
    notes = db.Column(db.Text)
    enregistre_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    depense = db.relationship("Depense")
    enregistre_par = db.relationship("User")


class Deplacement(db.Model):
    """Trajet (ex. taxi) enregistré directement par le secrétaire, avec son prix."""

    __tablename__ = "deplacements"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.now)
    trajet = db.Column(db.String(255), nullable=False)
    prix = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.Text)
    enregistre_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    enregistre_par = db.relationship("User")


class DemandeCarburant(db.Model):
    """Demande de réapprovisionnement en tickets de carburant."""

    __tablename__ = "demandes_carburant"

    id = db.Column(db.Integer, primary_key=True)
    date_demande = db.Column(db.DateTime, default=datetime.now)
    demande_par_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_au_moment = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text)
    statut = db.Column(db.String(20), nullable=False, default="en_attente")
    traite_le = db.Column(db.DateTime)
    traite_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    demande_par = db.relationship("User", foreign_keys=[demande_par_id])
    traite_par = db.relationship("User", foreign_keys=[traite_par_id])


class ArticleInventaire(db.Model):
    """Article physique suivi en stock (fourniture, produit d'entretien, matériel de bureau)."""

    __tablename__ = "articles_inventaire"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    categorie = db.Column(db.String(30), nullable=False)
    seuil_alerte = db.Column(db.Integer, nullable=False, default=0)
    actif = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (
        db.UniqueConstraint("nom", "categorie", name="uq_article_inventaire_nom_categorie"),
    )

    def __repr__(self):
        return f"<ArticleInventaire {self.nom}>"


class MouvementInventaire(db.Model):
    """Achat (entrée en stock) ou utilisation (sortie de stock) d'un article d'inventaire."""

    __tablename__ = "mouvements_inventaire"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles_inventaire.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.now)
    type_mouvement = db.Column(db.String(15), nullable=False)  # "achat" ou "utilisation"
    quantite = db.Column(db.Integer, nullable=False)
    prix_unitaire = db.Column(db.Numeric(12, 2))  # pour un achat
    montant = db.Column(db.Numeric(12, 2))  # quantite × prix_unitaire, reflété dans le Suivi mensuel
    beneficiaire = db.Column(db.String(150))
    notes = db.Column(db.Text)
    enregistre_par_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    article = db.relationship("ArticleInventaire", backref=db.backref("mouvements", lazy=True))
    enregistre_par = db.relationship("User")


class EvenementAgenda(db.Model):
    """Réunion ou événement ajouté par le secrétaire pour l'admin."""

    __tablename__ = "evenements_agenda"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(200), nullable=False)
    type_evenement = db.Column(db.String(20), nullable=False, default="reunion")
    date = db.Column(db.Date, nullable=False)
    heure_debut = db.Column(db.Time)
    heure_fin = db.Column(db.Time)
    lieu = db.Column(db.String(200))
    description = db.Column(db.Text)
    cree_par_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    vu_par_admin = db.Column(db.Boolean, default=False, nullable=False)
    annule = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cree_par = db.relationship("User")


class ClientCommercial(db.Model):
    """Fiche de suivi d'un prospect/client géré par un agent commercial."""

    __tablename__ = "clients_commercial"

    id = db.Column(db.Integer, primary_key=True)
    date_contact = db.Column(db.Date, nullable=False)
    nom_client = db.Column(db.String(150), nullable=False)
    telephone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    type_client = db.Column(db.String(20), nullable=False, default="acheteur")
    type_client_precision = db.Column(db.String(150))
    budget = db.Column(db.Numeric(14, 2))
    villa_interessee = db.Column(db.String(150))
    statut = db.Column(db.String(20), nullable=False, default="nouveau")
    prochaine_relance = db.Column(db.Date)
    notes = db.Column(db.Text)
    cree_par_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cree_par = db.relationship("User")
