"""change the column name from filed_id to field_id

Revision ID: 4315fe5e82fb
Revises: 6f2a730f32bf
Create Date: 2026-03-22 10:06:55.336966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4315fe5e82fb'
down_revision: Union[str, Sequence[str], None] = '6f2a730f32bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop constraints first using the names from your file
    op.drop_constraint('FK__mapping_r__dest___72C60C4A', 'mapping_rule', type_='foreignkey')
    op.drop_constraint('FK__mapping_r__src_f__73BA3083', 'mapping_rule', type_='foreignkey')

    # 2. Rename the column (this keeps your data!)
    op.alter_column('endpoint_fields', 'endpoint_filed_id', new_column_name='endpoint_field_id')

    # 3. Handle the Index rename (Drop old, Create new)
    op.drop_index('ix_endpoint_fields_endpoint_filed_id', table_name='endpoint_fields')
    op.create_index('ix_endpoint_fields_endpoint_field_id', 'endpoint_fields', ['endpoint_field_id'], unique=False)

    # 4. Re-create the foreign keys pointing to the NEW column name
    op.create_foreign_key(None, 'mapping_rule', 'endpoint_fields', ['src_field_id'], ['endpoint_field_id'])
    op.create_foreign_key(None, 'mapping_rule', 'endpoint_fields', ['dest_field_id'], ['endpoint_field_id'])


def downgrade() -> None:
    # Reverse foreign keys
    op.drop_constraint(None, 'mapping_rule', type_='foreignkey')
    op.drop_constraint(None, 'mapping_rule', type_='foreignkey')

    # Rename column back
    op.alter_column('endpoint_fields', 'endpoint_field_id', new_column_name='endpoint_filed_id')

    # Restore indices
    op.drop_index('ix_endpoint_fields_endpoint_field_id', table_name='endpoint_fields')
    op.create_index('ix_endpoint_fields_endpoint_filed_id', 'endpoint_fields', ['endpoint_filed_id'], unique=False)

    # Restore original foreign keys
    op.create_foreign_key('FK__mapping_r__src_f__73BA3083', 'mapping_rule', 'endpoint_fields', ['src_field_id'], ['endpoint_filed_id'])
    op.create_foreign_key('FK__mapping_r__dest___72C60C4A', 'mapping_rule', 'endpoint_fields', ['dest_field_id'], ['endpoint_filed_id'])

