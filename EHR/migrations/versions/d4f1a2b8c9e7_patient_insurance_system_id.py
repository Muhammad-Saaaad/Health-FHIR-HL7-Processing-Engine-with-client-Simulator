"""add insurance_system_id to patient

Revision ID: d4f1a2b8c9e7
Revises: ce2afcdd23a3
Create Date: 2026-05-18 00:00:00.000000

What this migration does (DATA-PRESERVING — no rows are modified):
- Adds a new nullable `insurance_system_id` (VARCHAR(50)) column to the `patient` table.
  Stores the Payer's system_id (e.g. "Payer-1") the patient is registered with, so the
  engine can later route claim-related messages to the correct insurer.

Pre-existing rows get `NULL` for this column. The application code only reads the column
where it exists and falls back to fan-out when it's NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f1a2b8c9e7'
down_revision: Union[str, Sequence[str], None] = 'ce2afcdd23a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'patient',
        sa.Column('insurance_system_id', sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('patient', 'insurance_system_id')