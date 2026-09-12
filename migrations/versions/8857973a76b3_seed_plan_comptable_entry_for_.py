"""Seed plan comptable entry for Consommables

Revision ID: 8857973a76b3
Revises: 02db2d0d966f
Create Date: 2026-09-12 15:14:56.128845

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8857973a76b3'
down_revision = '02db2d0d966f'
branch_labels = None
depends_on = None


def upgrade():
    # Si une catégorie "Consommables" existe déjà (créée via l'UI), on la retitre au numéro 6543.
    op.execute(
        "UPDATE plan_comptable SET numero = '6543' WHERE lower(nom) = lower('Consommables') AND numero <> '6543'"
    )
    # Sinon, et si 6543 n'est pas déjà pris par une autre catégorie, on la crée.
    op.execute(
        "INSERT INTO plan_comptable (numero, nom, actif, created_at) "
        "SELECT '6543', 'Consommables', true, CURRENT_TIMESTAMP "
        "WHERE NOT EXISTS (SELECT 1 FROM plan_comptable WHERE lower(nom) = lower('Consommables')) "
        "AND NOT EXISTS (SELECT 1 FROM plan_comptable WHERE numero = '6543')"
    )


def downgrade():
    op.execute("DELETE FROM plan_comptable WHERE numero = '6543' AND lower(nom) = lower('Consommables')")
