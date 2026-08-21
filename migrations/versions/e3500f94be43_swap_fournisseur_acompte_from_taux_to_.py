"""swap fournisseur acompte from taux to montant

Revision ID: e3500f94be43
Revises: 9d4499cb6e40
Create Date: 2026-08-20 11:37:57.432049

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3500f94be43'
down_revision = '9d4499cb6e40'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('montant_acompte', sa.Numeric(precision=14, scale=2), nullable=True))

    op.execute(
        "UPDATE fournisseurs SET montant_acompte = montant_marche * taux_acompte / 100 "
        "WHERE montant_marche IS NOT NULL AND taux_acompte IS NOT NULL"
    )

    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.drop_column('taux_acompte')


def downgrade():
    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('taux_acompte', sa.NUMERIC(precision=5, scale=2), autoincrement=False, nullable=True))

    op.execute(
        "UPDATE fournisseurs SET taux_acompte = montant_acompte / montant_marche * 100 "
        "WHERE montant_marche IS NOT NULL AND montant_marche != 0 AND montant_acompte IS NOT NULL"
    )

    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.drop_column('montant_acompte')
