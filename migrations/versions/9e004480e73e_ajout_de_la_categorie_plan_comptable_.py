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
    plan_comptable = sa.table(
        'plan_comptable',
        sa.column('numero', sa.String),
        sa.column('nom', sa.String),
        sa.column('actif', sa.Boolean),
    )
    op.execute(
        plan_comptable.insert().values(numero='6411', nom='Salaires', actif=True)
    )


def downgrade():
    op.execute("DELETE FROM plan_comptable WHERE nom = 'Salaires' AND numero = '6411'")
