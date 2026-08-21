"""rename fournisseur acompte fields to initial values

Revision ID: 35ea4e48ea93
Revises: ed222890e643
Create Date: 2026-08-20 12:08:25.705142

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '35ea4e48ea93'
down_revision = 'ed222890e643'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.alter_column('montant_acompte', new_column_name='montant_acompte_initial')
        batch_op.alter_column('date_versement', new_column_name='date_versement_initial')


def downgrade():
    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.alter_column('montant_acompte_initial', new_column_name='montant_acompte')
        batch_op.alter_column('date_versement_initial', new_column_name='date_versement')
