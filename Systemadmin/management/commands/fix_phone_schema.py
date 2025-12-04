"""
Management command to fix phone number schema issues in the database.

This command:
1. Checks if phone_number_id/contact_id columns exist in the tables
2. Adds the columns if they don't exist
3. Creates foreign key relationships to UniquePhoneNumber table

Usage:
    python manage.py fix_phone_schema
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Fix phone number schema by adding missing foreign key columns'

    def check_and_add_column(self, table_name, column_name, fk_table='systemadmin_unique_phone_number'):
        """Check if column exists and add it if it doesn't."""
        with connection.cursor() as cursor:
            # Check if column exists
            cursor.execute(f"""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = '{table_name}' 
                AND COLUMN_NAME = '{column_name}'
            """)
            column_exists = cursor.fetchone()[0] > 0
            
            if column_exists:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Column '{column_name}' already exists in '{table_name}'")
                )
                return True
            
            self.stdout.write(
                self.style.WARNING(f"✗ Column '{column_name}' does not exist in '{table_name}'")
            )
            self.stdout.write(f"  Adding column '{column_name}' to '{table_name}'...")
            
            try:
                # Add the column
                cursor.execute(f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN {column_name} BIGINT NULL
                """)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Column added successfully"))
                
                # Add foreign key constraint
                constraint_name = f"{table_name}_{column_name}_fk"
                cursor.execute(f"""
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY ({column_name}) REFERENCES {fk_table}(id)
                    ON DELETE CASCADE
                """)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Foreign key constraint added successfully"))
                
                # Add index
                index_name = f"{table_name}_{column_name}_idx"
                cursor.execute(f"""
                    CREATE INDEX {index_name}
                    ON {table_name}({column_name})
                """)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Index added successfully"))
                
                return True
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))
                return False

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("Phone Number Schema Fix"))
        self.stdout.write("=" * 60)
        self.stdout.write("")
        
        # Check and fix milkman table
        self.stdout.write("Checking milkman_milkman table...")
        self.check_and_add_column('milkman_milkman', 'phone_number_id')
        self.stdout.write("")
        
        # Check and fix customer table
        self.stdout.write("Checking customer_customer table...")
        self.check_and_add_column('customer_customer', 'contact_id')
        self.stdout.write("")
        
        # Check and fix vendor table
        self.stdout.write("Checking businessregistration_vendorbusinessregistration table...")
        self.check_and_add_column('businessregistration_vendorbusinessregistration', 'contact_id')
        self.stdout.write("")
        
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("Schema fix completed!"))
        self.stdout.write("=" * 60)
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write("1. Run: python manage.py migrate_phone_numbers --dry-run")
        self.stdout.write("2. If dry run looks good, run: python manage.py migrate_phone_numbers")
