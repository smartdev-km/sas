"""restructure fournisseurs for marche tracking

Revision ID: e80ec37ecab2
Revises: 083feb31f2f8
Create Date: 2026-08-20 11:20:25.038295

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e80ec37ecab2'
down_revision = '083feb31f2f8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.alter_column('nom', new_column_name='nom_societe')
        batch_op.add_column(sa.Column('numero_marche', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('date_signature', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('montant_marche', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column('taux_acompte', sa.Numeric(precision=5, scale=2), nullable=True))
        batch_op.add_column(sa.Column('date_versement', sa.Date(), nullable=True))
        batch_op.drop_column('telephone')
        batch_op.drop_column('contact')
        batch_op.drop_column('adresse')
        batch_op.drop_column('email')


def downgrade():
    with op.batch_alter_table('fournisseurs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.VARCHAR(length=120), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('adresse', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('contact', sa.VARCHAR(length=120), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('telephone', sa.VARCHAR(length=30), autoincrement=False, nullable=True))
        batch_op.drop_column('date_versement')
        batch_op.drop_column('taux_acompte')
        batch_op.drop_column('montant_marche')
        batch_op.drop_column('date_signature')
        batch_op.drop_column('numero_marche')
        batch_op.alter_column('nom_societe', new_column_name='nom')

    # ### end Alembic commands ###
