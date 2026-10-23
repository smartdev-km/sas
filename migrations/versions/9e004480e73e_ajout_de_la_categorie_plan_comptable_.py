"""Ajout de la categorie Plan comptable Salaires

Revision ID: 9e004480e73e
Revises: 593071ddb229
Create Date: 2026-10-22 20:53:49.302416

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9e004480e73e'
down_revision = '593071ddb229'
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent : certains environnements (ex. production) peuvent déjà avoir une
    # catégorie "Salaires" ajoutée manuellement via l'interface, avec ce même numéro.
    op.execute("""
        INSERT INTO plan_comptable (numero, nom, actif)
        SELECT '6411', 'Salaires', true
        WHERE NOT EXISTS (
            SELECT 1 FROM plan_comptable WHERE numero = '6411' OR nom = 'Salaires'
        )
    """)


def downgrade():
    op.execute("DELETE FROM plan_comptable WHERE nom = 'Salaires' AND numero = '6411'")
