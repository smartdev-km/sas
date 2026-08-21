import random
from datetime import date, timedelta
from decimal import Decimal

import click

from app import db
from app.models import User, Fournisseur, Depense, TransactionBancaire, Employe, Salaire, Appareil
from app.constants import CATEGORIES_DEPENSE, TYPES_CONTRAT, MODES_PAIEMENT, TYPES_APPAREIL

BENEFICIAIRES_DEMO = ["Client A", "Client B", "Client C", "Prestation ponctuelle"]

DEPARTEMENTS = ["Administration", "Opérations", "Commercial", "Technique"]
MARQUES_TELEPHONE = ["Samsung", "Tecno", "Infinix"]
MARQUES_ORDINATEUR = ["Dell", "HP", "Lenovo"]


def register(app):
    @app.cli.command("create-admin")
    @click.option("--nom", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(nom, email, password):
        """Crée un utilisateur administrateur."""
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            click.echo(f"Un utilisateur existe déjà avec l'email {email}.")
            return

        user = User(nom=nom, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrateur {email} créé avec succès.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Génère des données de démonstration pour le dashboard."""
        if Fournisseur.query.first():
            click.echo("Des données existent déjà, seed ignoré.")
            return

        fournisseurs = []
        for i in range(1, 6):
            montant_marche = Decimal(random.randint(500000, 3000000))
            taux_acompte = Decimal(random.choice([20, 30, 40]))
            fournisseurs.append(Fournisseur(
                nom_societe=f"Fournisseur {i}",
                numero_marche=f"MARCHE-{2026}-{i:03d}",
                date_signature=date.today() - timedelta(days=random.randint(30, 300)),
                montant_marche=montant_marche,
                montant_acompte_initial=montant_marche * taux_acompte / 100,
                actif=True,
            ))
        db.session.add_all(fournisseurs)
        db.session.flush()

        employes = [
            Employe(
                matricule=f"EMP-{i:04d}",
                nom=f"Employé {i}",
                poste="Agent",
                departement=random.choice(DEPARTEMENTS),
                salaire_base=Decimal(random.randint(1500, 4000)),
                telephone=f"+269 33{i} {1000 + i}",
                date_embauche=date.today() - timedelta(days=random.randint(30, 1000)),
                type_contrat=random.choice(TYPES_CONTRAT),
                mode_paiement=random.choice(MODES_PAIEMENT),
            )
            for i in range(1, 6)
        ]
        db.session.add_all(employes)
        db.session.flush()

        today = date.today()
        for offset in range(12):
            year = today.year
            month = today.month - offset
            while month <= 0:
                month += 12
                year -= 1
            month_date = date(year, month, 15)

            for _ in range(random.randint(3, 6)):
                db.session.add(Depense(
                    date=month_date - timedelta(days=random.randint(0, 10)),
                    montant=Decimal(random.randint(100, 3000)),
                    categorie=random.choice(CATEGORIES_DEPENSE),
                ))

            for _ in range(random.randint(2, 5)):
                db.session.add(TransactionBancaire(
                    date=month_date - timedelta(days=random.randint(0, 10)),
                    beneficiaire=random.choice(BENEFICIAIRES_DEMO),
                    libelle="Encaissement",
                    montant=Decimal(random.randint(500, 6000)),
                    sens="debit",
                ))

            for employe in employes:
                db.session.add(Salaire(
                    employe_id=employe.id,
                    mois=month,
                    annee=year,
                    montant=employe.salaire_base,
                    date_paiement=month_date,
                    statut="paye",
                ))

        # Appareils : un téléphone par employé, quelques ordinateurs, un en stock,
        # et un exemple de dommage + remplacement pour illustrer la fonctionnalité.
        for i, employe in enumerate(employes, start=1):
            db.session.add(Appareil(
                type_appareil="Téléphone",
                marque=random.choice(MARQUES_TELEPHONE),
                modele=f"Modèle {i}",
                numero_serie=f"TEL-{i:04d}",
                employe_id=employe.id,
                date_attribution=date.today() - timedelta(days=random.randint(30, 400)),
                statut="en_service",
            ))
            if i <= 3:
                db.session.add(Appareil(
                    type_appareil="Ordinateur portable",
                    marque=random.choice(MARQUES_ORDINATEUR),
                    modele=f"Latitude {i}",
                    numero_serie=f"PC-{i:04d}",
                    employe_id=employe.id,
                    date_attribution=date.today() - timedelta(days=random.randint(30, 400)),
                    statut="en_service",
                ))

        db.session.add(Appareil(
            type_appareil="Tablette",
            marque="Samsung",
            modele="Galaxy Tab",
            numero_serie="TAB-0001",
            employe_id=None,
            statut="en_service",
        ))

        premier_employe = employes[0]
        ancien_telephone = Appareil(
            type_appareil="Téléphone",
            marque="Tecno",
            modele="Spark 8",
            numero_serie="TEL-OLD-01",
            employe_id=premier_employe.id,
            date_attribution=date.today() - timedelta(days=200),
            statut="endommage",
            notes="[Démo] Écran fissuré suite à une chute.",
        )
        db.session.add(ancien_telephone)
        db.session.flush()

        nouveau_telephone = Appareil(
            type_appareil="Téléphone",
            marque="Samsung",
            modele="Galaxy A15",
            numero_serie="TEL-NEW-01",
            employe_id=premier_employe.id,
            date_attribution=date.today() - timedelta(days=5),
            statut="en_service",
        )
        db.session.add(nouveau_telephone)
        db.session.flush()

        ancien_telephone.statut = "remplace"
        ancien_telephone.remplace_par_id = nouveau_telephone.id

        db.session.commit()
        click.echo("Données de démonstration créées avec succès.")
