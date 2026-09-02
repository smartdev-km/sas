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
