"""change the fileds to fields

Revision ID: 6f2a730f32bf
Revises: f32599272c24
Create Date: 2026-03-22 09:35:32.559925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f2a730f32bf'
down_revision: Union[str, Sequence[str], None] = 'f32599272c24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the foreign keys
    op.drop_constraint('FK__mapping_r__dest___59FA5E80', 'mapping_rule', type_='foreignkey')
    op.drop_constraint('FK__mapping_r__src_f__59063A47', 'mapping_rule', type_='foreignkey')

    # 2. Drop the old index BEFORE renaming the table
    op.drop_index('ix_endpoint_fileds_endpoint_filed_id', table_name='endpoint_fileds')

    # 3. Rename the table
    op.rename_table('endpoint_fileds', 'endpoint_fields')

    # 4. Create the new index on the new table
    op.create_index('ix_endpoint_fields_endpoint_filed_id', 'endpoint_fields', ['endpoint_filed_id'], unique=False)

    # 5. Re-create the foreign keys
    op.create_foreign_key(None, 'mapping_rule', 'endpoint_fields', ['dest_field_id'], ['endpoint_filed_id'])
    op.create_foreign_key(None, 'mapping_rule', 'endpoint_fields', ['src_field_id'], ['endpoint_filed_id'])


def downgrade() -> None:
    # Undo the foreign keys
    op.drop_constraint(None, 'mapping_rule', type_='foreignkey')
    op.drop_constraint(None, 'mapping_rule', type_='foreignkey')

    # Rename back
    op.rename_table('endpoint_fields', 'endpoint_fileds')

    # Restore original foreign keys
    op.create_foreign_key('FK__mapping_r__src_f__59063A47', 'mapping_rule', 'endpoint_fileds', ['src_field_id'], ['endpoint_filed_id'])
    op.create_foreign_key('FK__mapping_r__dest___59FA5E80', 'mapping_rule', 'endpoint_fileds', ['dest_field_id'], ['endpoint_filed_id'])
