# SAS

Système de gestion administrative et financière pour une société de projet, développé avec Flask.

## Fonctionnalités

- **Dépenses** — suivi des dépenses par catégorie, paiement en cash ou par virement bancaire, validation par un administrateur
- **Compte Bancaire** — journal des mouvements du compte (débit/crédit), solde courant, report du solde initial
- **Fournisseurs** — suivi des marchés fournisseurs, acomptes, factures et taux d'exécution
- **Salaires** — génération des bulletins, workflow de validation en 3 étapes (secrétaire → admin → comptable), paiement cash ou virement
- **Consommables** — suivi mensuel des achats et paiements récurrents
- **Présence** — appel automatique/manuel des employés, horaires programmés, situation de présence mensuelle
- **Appareils** — suivi du parc d'appareils de l'entreprise (attribution, réparation, remplacement)
- **Rapport mensuel** — vue d'ensemble consolidée (dépenses, compte bancaire, fournisseurs, salaires, présence)

## Rôles

- **Admin** — accès complet, validation des opérations sensibles
- **Comptable** — dépenses, compte bancaire, consommables, paiement des salaires validés
- **Secrétaire** — génération des bulletins de salaire, rapports
- **Employé** (portail dédié) — présence, appareils, profil

## Stack technique

- Flask 3 / Flask-SQLAlchemy / Flask-Migrate (Alembic) / Flask-Login
- PostgreSQL
- Bootstrap 5 (templates Jinja2)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# éditer .env : SECRET_KEY, DATABASE_URL

flask db upgrade
flask run
```

## Déploiement

Le projet est prêt pour un déploiement sur Render.com (`Procfile`, `runtime.txt`, normalisation de l'URL `postgres://`). Variables d'environnement requises : `SECRET_KEY`, `DATABASE_URL`.
