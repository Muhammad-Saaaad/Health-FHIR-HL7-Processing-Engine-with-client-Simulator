"""patient unique (insurance_id, nic) when nic is present

Revision ID: c8e3b2d5a1f4
Revises: 78e19f517d6b
Create Date: 2026-05-18 00:00:00.000000

What this migration does (DATA-PRESERVING — no rows are deleted):
- Adds a UNIQUE constraint on `Patient(insurance_id, nic)` so the SAME nic
  cannot be registered twice under the SAME insurer. The same nic CAN appear
  under DIFFERENT insurers (multi-tenant). `nic` is nullable, so we use a
  filtered unique index (`WHERE nic IS NOT NULL`) — a plain UNIQUE constraint
  in SQL Server treats two NULLs as equal and would block a second patient
  with no NIC at all.

Pre-condition: there must be NO existing duplicates of (insurance_id, nic)
where nic IS NOT NULL. If there are, this migration will fail — deduplicate
the rows first, then re-run.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8e3b2d5a1f4'
down_revision: Union[str, Sequence[str], None] = '78e19f517d6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQL Server filtered unique index: enforces uniqueness ONLY for rows where nic IS NOT NULL.
    # This matches the SQLAlchemy `UniqueConstraint('insurance_id', 'nic', name='uq_insurance_nic')`
    # at the application level — the model declaration is informational; the actual DB-level
    # uniqueness comes from this filtered index.
    op.execute("""
        CREATE UNIQUE INDEX uq_insurance_nic
        ON dbo.[Patient] (insurance_id, nic)
        WHERE nic IS NOT NULL;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX uq_insurance_nic ON dbo.[Patient];")
