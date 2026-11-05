CATEGORIES_DEPENSE = ["Loyer", "Fournitures", "Transport", "Marketing", "Logiciels", "Réparation", "Consommables", "Salaires", "Divers"]

MOIS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

STATUTS_SALAIRE = {
    "en_attente": "En attente",
    "valide": "Validé",
    "paye": "Payé",
}

SEXES = {
    "H": "Homme",
    "F": "Femme",
}

TYPES_CONTRAT = ["CDI", "CDD", "Stage", "Consultant"]

MOTIFS_ABSENCE = {
    "conge": "Congé",
    "maladie": "Maladie",
    "empechement": "Empêchement",
    "autre": "Autre",
}

STATUTS_DEMANDE_ABSENCE = {
    "en_attente": "En attente",
    "validee": "Validée",
    "refusee": "Refusée",
}

MOTIFS_ABSENCE_BULLETIN = {
    "jour_ferie": "Jour férié (congés payés)",
    "maladie_justificatif": "Congés maladie avec justificatif",
    "absence_justifiee": "Absence justifiée",
    "absence_autorisee": "Absence autorisée",
}

TYPES_EVENEMENT = {
    "reunion": "Réunion",
    "rdv_externe": "Rendez-vous externe",
    "formation": "Formation",
    "autre": "Autre",
}

MODES_PAIEMENT = ["Virement bancaire", "Mobile money", "Espèces"]

ROLES_COMPTE = {
    "admin": "Administrateur",
    "comptable": "RAF",
    "secretaire": "Secrétaire",
    "employe": "Employée",
    "agent_commercial": "Agent commercial",
}

TYPES_CLIENT = {
    "investisseur": "Investisseur",
    "famille": "Famille",
    "autre": "Autre",
}

STATUTS_CLIENT = {
    "nouveau": "Nouveau",
    "contacte": "Contacté",
    "rdv_cale": "RDV calé",
    "reservee": "Réservée",
    "prochaine_relance": "Prochaine relance",
    "confirme": "Confirmé",
    "vendu": "Vendu",
}

STATUTS_CLIENT_COULEUR = {
    "nouveau": "secondary",
    "contacte": "info",
    "rdv_cale": "primary",
    "reservee": "warning",
    "prochaine_relance": "warning",
    "confirme": "success",
    "vendu": "success",
}

PROJETS_ACQUISITION = {
    "residence_principale": "Résidence principale",
    "residence_secondaire": "Résidence secondaire",
    "investissement_locatif": "Investissement locatif",
    "investissement_patrimonial": "Investissement patrimonial",
    "autre": "Autre",
}

MODES_FINANCEMENT = {
    "fonds_propres": "Fonds propres",
    "credit_bancaire": "Crédit bancaire",
    "paiement_echelonne": "Paiement échelonné",
    "revenus_mensuels": "Revenus mensuels (CDD, CDI, allocations familiales, ou autres)",
}

INTENTIONS_ACHAT = {
    "reserver_maintenant": "Je souhaite réserver une villa dès maintenant avec signature de compromis de vente",
    "apres_jeux": "Je souhaite concrétiser mon achat après les jeux, sous réserve de disponibilité",
}

TYPES_APPAREIL = ["Téléphone", "Ordinateur portable", "Ordinateur fixe", "Tablette", "Imprimante", "Autre"]

STATUTS_APPAREIL = {
    "en_service": "En service",
    "endommage": "Endommagé",
    "remplace": "Remplacé",
    "hors_service": "Hors service",
}

STATUTS_DEMANDE_APPAREIL = {
    "en_attente": "En attente",
    "traitee": "Traitée",
    "rejetee": "Rejetée",
}

TYPES_GAZ = {
    "essence": "Essence",
    "diesel": "Gazoil",
}

PRIX_CARBURANT = {
    "essence": 750,
    "diesel": 650,
}

CATEGORIES_INVENTAIRE = {
    "fournitures": "Fournitures",
    "produits_entretien": "Produits d'entretien",
    "materiel_bureau": "Matériel de bureau",
}

TYPES_HISTORIQUE_APPAREIL = {
    "creation": {"label": "Ajouté", "icone": "bi-plus-circle", "couleur": "primary"},
    "attribution": {"label": "Attribution", "icone": "bi-person-check", "couleur": "primary"},
    "demande": {"label": "Signalement employé", "icone": "bi-flag", "couleur": "warning"},
    "endommage": {"label": "Endommagé", "icone": "bi-exclamation-triangle", "couleur": "danger"},
    "reparation": {"label": "Réparé", "icone": "bi-tools", "couleur": "success"},
    "remplacement": {"label": "Remplacé", "icone": "bi-arrow-repeat", "couleur": "secondary"},
    "hors_service": {"label": "Hors service", "icone": "bi-power", "couleur": "dark"},
    "rejet": {"label": "Demande rejetée", "icone": "bi-x-circle", "couleur": "secondary"},
}
