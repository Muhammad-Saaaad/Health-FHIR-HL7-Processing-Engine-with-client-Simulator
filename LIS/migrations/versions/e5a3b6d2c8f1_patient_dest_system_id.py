"""add dest_system_id to patient

Revision ID: e5a3b6d2c8f1
Revises: b7d2a1c4f9e3
Create Date: 2026-05-18 00:00:01.000000

What this migration does (DATA-PRESERVING — no rows are modified):
- Adds a nullable `dest_system_id` (VARCHAR(50)) column to the `patient` table.
  Stores the originating EHR's system_id (e.g. "EHR-1"). When the LIS sends data back
  (lab results, etc.), this is used as MSH-5 in the outgoing HL7 message so the engine
  routes the reply to the correct EHR.

Pre-existing patient rows get `NULL` for this column. Replies for those patients will
fan out to all EHR destinations (legacy behavior) until the column is backfilled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a3b6d2c8f1'
down_revision: Union[str, Sequence[str], None] = 'b7d2a1c4f9e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'patient',
        sa.Column('dest_system_id', sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('patient', 'dest_system_id')