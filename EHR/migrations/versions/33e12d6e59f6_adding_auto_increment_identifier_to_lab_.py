"""adding auto-increment identifier to lab report

Revision ID: 33e12d6e59f6
Revises: 7f5f2a1ba0c1
Create Date: 2026-04-07 12:55:00.519732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33e12d6e59f6'
down_revision: Union[str, Sequence[str], None] = '7f5f2a1ba0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop index if it exists
    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_lab_report_report_id')
            DROP INDEX ix_lab_report_report_id ON lab_report
    """)
    
    # Drop foreign key if it exists
    op.execute("""
        IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                   WHERE TABLE_NAME = 'mini_test_result' AND CONSTRAINT_TYPE = 'FOREIGN KEY'
                   AND CONSTRAINT_NAME LIKE 'FK__mini_test__repor%')
            ALTER TABLE mini_test_result 
            DROP CONSTRAINT FK__mini_test__repor__72C60C4A
    """)
    
    # Drop primary key by finding the actual constraint name
    op.execute("""
        DECLARE @PK_Name NVARCHAR(128) = (
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
            WHERE TABLE_NAME = 'lab_report' AND CONSTRAINT_TYPE = 'PRIMARY KEY'
        )
        IF @PK_Name IS NOT NULL
            EXEC ('ALTER TABLE lab_report DROP CONSTRAINT [' + @PK_Name + ']')
    """)
    
    # Drop and recreate column with IDENTITY
    op.execute("""
        ALTER TABLE lab_report DROP COLUMN report_id
    """)
    
    op.execute("""
        ALTER TABLE lab_report 
        ADD report_id INT IDENTITY(1,1) PRIMARY KEY
    """)
    
    # Recreate foreign key
    op.execute("""
        ALTER TABLE mini_test_result 
        ADD CONSTRAINT FK__mini_test__repor__72C60C4A FOREIGN KEY (report_id) 
        REFERENCES lab_report(report_id)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop foreign key
    op.execute("""
        IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                   WHERE TABLE_NAME = 'mini_test_result' AND CONSTRAINT_TYPE = 'FOREIGN KEY'
                   AND CONSTRAINT_NAME LIKE 'FK__mini_test__repor%')
            ALTER TABLE mini_test_result
            DROP CONSTRAINT FK__mini_test__repor__72C60C4A
    """)

    # Drop index if it exists
    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_lab_report_report_id')
            DROP INDEX ix_lab_report_report_id ON lab_report
    """)

    # Drop primary key by finding the actual constraint name
    op.execute("""
        DECLARE @PK_Name NVARCHAR(128) = (
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
            WHERE TABLE_NAME = 'lab_report' AND CONSTRAINT_TYPE = 'PRIMARY KEY'
        )
        IF @PK_Name IS NOT NULL
            EXEC ('ALTER TABLE lab_report DROP CONSTRAINT [' + @PK_Name + ']')
    """)

    op.execute("""
        ALTER TABLE lab_report DROP COLUMN report_id
    """)
    
    op.execute("""
        ALTER TABLE lab_report
        ADD report_id INT NOT NULL
    """)

    op.execute("""
        ALTER TABLE lab_report
        ADD CONSTRAINT PK_lab_report_id PRIMARY KEY (report_id)
    """)

    # Recreate foreign key
    op.execute("""
        ALTER TABLE mini_test_result
        ADD CONSTRAINT FK__mini_test__repor__72C60C4A FOREIGN KEY (report_id)
        REFERENCES lab_report(report_id)
    """)