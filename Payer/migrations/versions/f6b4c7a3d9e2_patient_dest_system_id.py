"""add dest_system_id to Patient

Revision ID: f6b4c7a3d9e2
Revises: c8e3b2d5a1f4
Create Date: 2026-05-18 00:00:02.000000

What this migration does (DATA-PRESERVING — no rows are modified):
- Adds a nullable `dest_system_id` (VARCHAR(50)) column to the `Patient` table.
  Stores the originating EHR's system_id (e.g. "EHR-1"). When the Payer sends a claim
  response back, this is used as MSH-5 in the outgoing HL7 message so the engine
  routes the reply to the correct EHR.

Pre-existing patient rows get `NULL` for this column. Their claim responses will fan
out to all EHR-category destinations (legacy behavior) until the column is backfilled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6b4c7a3d9e2'
down_revision: Union[str, Sequence[str], None] = 'c8e3b2d5a1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'Patient',
        sa.Column('dest_system_id', sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('Patient', 'dest_system_id')