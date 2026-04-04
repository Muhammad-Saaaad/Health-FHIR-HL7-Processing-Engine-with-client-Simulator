"""change the id of the primary key for those tables, whose keys were comming from the engine.

Revision ID: 3ef826733c11
Revises: 923caa7d6f0f
Create Date: 2026-04-04 11:54:36.121674

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ef826733c11'
down_revision: Union[str, Sequence[str], None] = '923caa7d6f0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop FK dependencies first.
    op.drop_constraint('FK__lab_repor__visit__534D60F1', 'lab_report', type_='foreignkey')
    op.drop_constraint('FK__visiting___docto__5070F446', 'visiting_notes', type_='foreignkey')
    op.drop_constraint('FK__visiting_no__mpi__4F7CD00D', 'visiting_notes', type_='foreignkey')

    # Drop PK constraints before changing PK column types.
    op.drop_constraint('PK__doctor__F39935642DAF6529', 'doctor', type_='primary')
    op.drop_constraint('PK__patient__DF50F7D4D7D59B4F', 'patient', type_='primary')
    op.drop_constraint('PK__visiting__CEDD0FA437E1AC6F', 'visiting_notes', type_='primary')

    # Drop indexes that depend on the columns being changed.
    op.drop_index('ix_doctor_doctor_id', table_name='doctor')
    op.drop_index('ix_patient_mpi', table_name='patient')
    op.drop_index('ix_visiting_notes_note_id', table_name='visiting_notes')

    # SQL Server does not allow changing IDENTITY INT columns directly to VARCHAR.
    # Migrate identity-based keys using temp columns, copy data, drop old columns, then rename.
    op.add_column('doctor', sa.Column('doctor_id_tmp', sa.String(length=20), nullable=True))
    op.execute("UPDATE doctor SET doctor_id_tmp = CONVERT(VARCHAR(20), doctor_id)")
    op.drop_column('doctor', 'doctor_id')
    op.execute("EXEC sp_rename 'doctor.doctor_id_tmp', 'doctor_id', 'COLUMN'")
    op.execute("ALTER TABLE doctor ALTER COLUMN doctor_id VARCHAR(20) NOT NULL")

    op.add_column('patient', sa.Column('mpi_tmp', sa.String(length=20), nullable=True))
    op.execute("UPDATE patient SET mpi_tmp = CONVERT(VARCHAR(20), mpi)")
    op.drop_column('patient', 'mpi')
    op.execute("EXEC sp_rename 'patient.mpi_tmp', 'mpi', 'COLUMN'")
    op.execute("ALTER TABLE patient ALTER COLUMN mpi VARCHAR(20) NOT NULL")

    op.add_column('visiting_notes', sa.Column('note_id_tmp', sa.String(length=20), nullable=True))
    op.execute("UPDATE visiting_notes SET note_id_tmp = CONVERT(VARCHAR(20), note_id)")
    op.drop_column('visiting_notes', 'note_id')
    op.execute("EXEC sp_rename 'visiting_notes.note_id_tmp', 'note_id', 'COLUMN'")
    op.execute("ALTER TABLE visiting_notes ALTER COLUMN note_id VARCHAR(20) NOT NULL")

    # Non-identity FK columns can be altered directly once dependent constraints are dropped.
    op.execute("ALTER TABLE visiting_notes ALTER COLUMN mpi VARCHAR(20) NOT NULL")
    op.execute("ALTER TABLE visiting_notes ALTER COLUMN doctor_id VARCHAR(20) NOT NULL")
    op.execute("ALTER TABLE lab_report ALTER COLUMN visit_id VARCHAR(20) NOT NULL")

    # Recreate PK constraints and indexes.
    op.create_primary_key('doctor_pkey', 'doctor', ['doctor_id'])
    op.create_primary_key('patient_pkey', 'patient', ['mpi'])
    op.create_primary_key('visiting_notes_pkey', 'visiting_notes', ['note_id'])

    op.create_index('ix_doctor_doctor_id', 'doctor', ['doctor_id'], unique=False)
    op.create_index('ix_patient_mpi', 'patient', ['mpi'], unique=False)
    op.create_index('ix_visiting_notes_note_id', 'visiting_notes', ['note_id'], unique=False)

    # Recreate FK constraints.
    op.create_foreign_key('visiting_notes_mpi_fkey', 'visiting_notes', 'patient', ['mpi'], ['mpi'])
    op.create_foreign_key('visiting_notes_doctor_id_fkey', 'visiting_notes', 'doctor', ['doctor_id'], ['doctor_id'])
    op.create_foreign_key('lab_report_visit_id_fkey', 'lab_report', 'visiting_notes', ['visit_id'], ['note_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop FK dependencies first.
    op.drop_constraint('lab_report_visit_id_fkey', 'lab_report', type_='foreignkey')
    op.drop_constraint('visiting_notes_doctor_id_fkey', 'visiting_notes', type_='foreignkey')
    op.drop_constraint('visiting_notes_mpi_fkey', 'visiting_notes', type_='foreignkey')

    # Drop PK constraints and dependent indexes.
    op.drop_constraint('doctor_pkey', 'doctor', type_='primary')
    op.drop_constraint('patient_pkey', 'patient', type_='primary')
    op.drop_constraint('visiting_notes_pkey', 'visiting_notes', type_='primary')

    op.drop_index('ix_doctor_doctor_id', table_name='doctor')
    op.drop_index('ix_patient_mpi', table_name='patient')
    op.drop_index('ix_visiting_notes_note_id', table_name='visiting_notes')

    # SQL Server conversion from string to int requires values to be numeric.
    op.execute("ALTER TABLE doctor ALTER COLUMN doctor_id INT NOT NULL")
    op.execute("ALTER TABLE patient ALTER COLUMN mpi INT NOT NULL")
    op.execute("ALTER TABLE visiting_notes ALTER COLUMN note_id INT NOT NULL")
    op.execute("ALTER TABLE visiting_notes ALTER COLUMN mpi INT NOT NULL")
    op.execute("ALTER TABLE visiting_notes ALTER COLUMN doctor_id INT NOT NULL")
    op.execute("ALTER TABLE lab_report ALTER COLUMN visit_id INT NOT NULL")

    # Recreate PK constraints, indexes, and FKs.
    op.create_primary_key('doctor_pkey', 'doctor', ['doctor_id'])
    op.create_primary_key('patient_pkey', 'patient', ['mpi'])
    op.create_primary_key('visiting_notes_pkey', 'visiting_notes', ['note_id'])

    op.create_index('ix_doctor_doctor_id', 'doctor', ['doctor_id'], unique=False)
    op.create_index('ix_patient_mpi', 'patient', ['mpi'], unique=False)
    op.create_index('ix_visiting_notes_note_id', 'visiting_notes', ['note_id'], unique=False)

    op.create_foreign_key('visiting_notes_mpi_fkey', 'visiting_notes', 'patient', ['mpi'], ['mpi'])
    op.create_foreign_key('visiting_notes_doctor_id_fkey', 'visiting_notes', 'doctor', ['doctor_id'], ['doctor_id'])
    op.create_foreign_key('lab_report_visit_id_fkey', 'lab_report', 'visiting_notes', ['visit_id'], ['note_id'])
