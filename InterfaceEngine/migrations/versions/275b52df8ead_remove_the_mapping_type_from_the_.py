"""remove the mapping type from the endpoint fields table

Revision ID: 275b52df8ead
Revises: b41d120cc03c
Create Date: 2026-04-07 10:19:35.768485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '275b52df8ead'
down_revision: Union[str, Sequence[str], None] = 'b41d120cc03c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQL Server keeps a named default constraint on the column, so it must be
    # removed before the column can be dropped.
    op.execute(
        """
        DECLARE @constraint_name sysname;
        SELECT @constraint_name = dc.name
        FROM sys.default_constraints dc
        JOIN sys.columns c ON c.default_object_id = dc.object_id
        JOIN sys.tables t ON t.object_id = c.object_id
        WHERE t.name = 'endpoint_fields'
          AND c.name = 'mapping_type';

        IF @constraint_name IS NOT NULL
        BEGIN
            EXEC('ALTER TABLE dbo.endpoint_fields DROP CONSTRAINT [' + @constraint_name + ']');
        END
        """
    )
    op.drop_column('endpoint_fields', 'mapping_type')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('endpoint_fields', sa.Column('mapping_type', sa.VARCHAR(length=15, collation='SQL_Latin1_General_CP1_CI_AS'), server_default=sa.text("('Scalar')"), autoincrement=False, nullable=False))
