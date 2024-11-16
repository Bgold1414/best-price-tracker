"""Add target_price to wishlist

Revision ID: f32c24b5f827
Revises: 
Create Date: 2024-11-01 13:17:55.760345

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f32c24b5f827'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wishlist', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_price', sa.Float(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wishlist', schema=None) as batch_op:
        batch_op.drop_column('target_price')

    # ### end Alembic commands ###
