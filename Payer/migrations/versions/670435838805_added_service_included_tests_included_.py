"""Added service_included, tests_included and mpi cols and remove pid and service name

Revision ID: 670435838805
Revises: 6f2cf6f553a9
Create Date: 2026-04-20 11:33:44.137259

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '670435838805'
down_revision: Union[str, Sequence[str], None] = '6f2cf6f553a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("Patient_Claim", "service_name")
    op.drop_column("Patient_Claim", "provider_phone_no")

    op.add_column("Patient_Claim", sa.Column("service_included", sa.Boolean(), nullable=False, default=False))
    op.add_column("Patient_Claim", sa.Column("tests_included", sa.Boolean(), nullable=False, default=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("Patient_Claim", "service_included")
    op.drop_column("Patient_Claim", "tests_included")

    op.add_column("Patient_Claim", sa.Column("provider_phone_no", sa.VARCHAR(length=20), nullable=True))
    op.add_column("Patient_Claim", sa.Column("service_name", sa.VARCHAR(length=100), nullable=False))
