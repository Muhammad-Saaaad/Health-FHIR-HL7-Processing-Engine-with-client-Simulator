from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9a67d79f6ee1'
down_revision: Union[str, Sequence[str], None] = '770fe2336a07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns as NULLABLE first to avoid SQL Server NOT NULL constraint error
    op.add_column('bill', sa.Column('consultation_amount', sa.Float(), nullable=True))
    op.add_column('bill', sa.Column('lab_charges', sa.Float(), nullable=True))

    # 2. DATA MIGRATION: Move existing data before dropping old columns

    # Transfer insurance_amount → consultation_amount
    op.execute("UPDATE bill SET consultation_amount = insurance_amount")

    # Transfer lab_charges from visiting_notes → bill
    # FIXED: removed corrupted markdown link [vn.id](http://vn.id) → plain vn.id
    # NOTE: adjust the JOIN condition below if your FK is visiting_notes.bill_id instead of bill.visit_id
    op.execute("""
        UPDATE b
        SET b.lab_charges = vn.lab_charges
        FROM bill b
        JOIN visiting_notes vn ON vn.bill_id = b.bill_id
    """)

    # 3. CLEANUP: Handle any remaining NULLs before enforcing NOT NULL
    op.execute("UPDATE bill SET consultation_amount = 0.0 WHERE consultation_amount IS NULL")
    op.execute("UPDATE bill SET lab_charges = 0.0 WHERE lab_charges IS NULL")

    # 4. ENFORCE CONSTRAINTS: Now safely make consultation_amount NOT NULL
    # FIXED: added existing_type= — required by SQL Server when altering nullability
    op.alter_column(
        'bill',
        'consultation_amount',
        existing_type=sa.Float(),
        nullable=False
    )
    # lab_charges stays nullable=True (safer — not all visits have lab tests)

    # 5. REMOVE OLD SCHEMA
    op.drop_column('bill', 'insurance_amount')
    op.drop_column('visiting_notes', 'lab_charges')


def downgrade() -> None:
    # 1. Restore old columns as nullable first
    op.add_column('visiting_notes', sa.Column('lab_charges', sa.Float(), nullable=True))
    op.add_column('bill', sa.Column('insurance_amount', sa.Float(), nullable=True))

    # 2. DATA REVERSION: Move data back to original columns

    # Transfer consultation_amount → insurance_amount
    op.execute("UPDATE bill SET insurance_amount = consultation_amount")

    # Transfer lab_charges from bill → visiting_notes
    # FIXED: removed corrupted markdown link [vn.id](http://vn.id) → plain vn.id
    op.execute("""
        UPDATE vn
        SET vn.lab_charges = b.lab_charges
        FROM visiting_notes vn
        JOIN bill b ON vn.bill_id = b.bill_id
    """)

    # 3. Enforce NOT NULL on restored insurance_amount
    # FIXED: added existing_type= — required by SQL Server when altering nullability
    op.alter_column(
        'bill',
        'insurance_amount',
        existing_type=sa.Float(),
        nullable=False
    )

    # 4. Drop the new columns added in upgrade
    op.drop_column('bill', 'lab_charges')
    op.drop_column('bill', 'consultation_amount')