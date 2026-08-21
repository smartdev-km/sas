"""rename facture montant_brut to montant_net_paye

Revision ID: ed222890e643
Revises: e3500f94be43
Create Date: 2026-08-20 11:56:01.329485

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed222890e643'
down_revision = 'e3500f94be43'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('factures_fournisseur', schema=None) as batch_op:
        batch_op.alter_column('montant_brut', new_column_name='montant_net_paye')


def downgrade():
    with op.batch_alter_table('factures_fournisseur', schema=None) as batch_op:
        batch_op.alter_column('montant_net_paye', new_column_name='montant_brut')
