"""patient composite PK (nic, lab_id) for multi-tenant patients

Revision ID: b7d2a1c4f9e3
Revises: 4eab6758e4b9
Create Date: 2026-05-18 00:00:00.000000

What this migration does (DATA-PRESERVING — no rows are deleted):
- Drops the single-column PK on `patient.nic` and the now-redundant
  UniqueConstraint('lab_id', 'nic').
- Creates a composite PK on `patient(nic, lab_id)` so the SAME nic can
  legitimately exist in MULTIPLE labs.
- Drops the single-column FK `test_request.nic -> patient.nic` and replaces
  it with a composite FK on `test_request(nic, lab_id) -> patient(nic, lab_id)`.
- Drops the single-column FK `test_billing.nic -> patient.nic`. (test_billing
  has no `lab_id` column, so the patient is reached via `test_req` -> patient.
  `nic` stays on test_billing as a denormalized column with no FK enforcement.)

Pre-condition: every `test_request` row's `lab_id` must match its patient's
`lab_id`. If any rows violate this, the composite FK creation at step 6 will
fail and the migration will roll back — fix the data first, then re-run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2a1c4f9e3'
down_revision: Union[str, Sequence[str], None] = '4eab6758e4b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Drop the redundant UNIQUE constraint (it will be replaced by the composite PK).
    op.drop_constraint('uq_lab_nic', 'patient', type_='unique')

    # 2. Drop FK on test_request.nic (replaced by composite FK below).
    op.drop_constraint('fk_testreq_patient_nic', 'test_request', type_='foreignkey')

    # 3. Drop FK on test_billing.nic (no replacement; patient is reachable via test_req).
    op.drop_constraint('fk_test_billing_patient_nic', 'test_billing', type_='foreignkey')

    # 4. Drop the existing PK on patient. SQL Server auto-names PKs (e.g. PK__patient__...),
    #    so we look it up dynamically and drop it by name. T-SQL requires building the
    #    statement into a variable before EXEC sp_executesql — `EXEC('...' + var)` is invalid.
    op.execute("""
        DECLARE @pk_name SYSNAME;
        DECLARE @sql NVARCHAR(MAX);
        SELECT @pk_name = name
        FROM sys.key_constraints
        WHERE type = 'PK' AND parent_object_id = OBJECT_ID('dbo.patient');
        IF @pk_name IS NOT NULL
        BEGIN
            SET @sql = N'ALTER TABLE dbo.patient DROP CONSTRAINT ' + QUOTENAME(@pk_name);
            EXEC sp_executesql @sql;
        END
    """)

    # 5. Add the composite PK on (nic, lab_id).
    op.create_primary_key('pk_patient_nic_lab', 'patient', ['nic', 'lab_id'])

    # 6. Add the composite FK from test_request -> patient.
    op.create_foreign_key(
        'fk_testreq_patient_nic_lab',
        source_table='test_request',
        referent_table='patient',
        local_cols=['nic', 'lab_id'],
        remote_cols=['nic', 'lab_id'],
    )


def downgrade() -> None:
    """Downgrade schema.

    WARNING: If you have rows in `patient` where the same NIC exists in multiple
    labs, this downgrade will FAIL when recreating the single-column PK on `nic`.
    That is intended — those rows are exactly what the composite PK was meant
    to allow. Resolve the duplicates manually before downgrading.
    """
    # Reverse step 6: drop composite FK.
    op.drop_constraint('fk_testreq_patient_nic_lab', 'test_request', type_='foreignkey')

    # Reverse step 5: drop composite PK.
    op.drop_constraint('pk_patient_nic_lab', 'patient', type_='primary')

    # Reverse step 4: restore single-column PK on nic.
    op.create_primary_key('pk_patient', 'patient', ['nic'])

    # Reverse step 3: restore FK on test_billing.nic.
    op.create_foreign_key(
        'fk_test_billing_patient_nic',
        source_table='test_billing',
        referent_table='patient',
        local_cols=['nic'],
        remote_cols=['nic'],
    )

    # Reverse step 2: restore FK on test_request.nic.
    op.create_foreign_key(
        'fk_testreq_patient_nic',
        source_table='test_request',
        referent_table='patient',
        local_cols=['nic'],
        remote_cols=['nic'],
    )

    # Reverse step 1: restore the redundant unique constraint.
    op.create_unique_constraint('uq_lab_nic', 'patient', ['lab_id', 'nic'])