"""
Management command to migrate existing phone numbers from Vendor, Milkman, and Customer models
to the centralized UniquePhoneNumber table.

Usage:
    python manage.py migrate_phone_numbers [--dry-run]
"""

import logging
import traceback

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.db.models import Q

from Systemadmin.models import UniquePhoneNumber

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate existing phone numbers from all user models to UniquePhoneNumber table'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Run migration without actually saving data',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be saved'))

        self.stdout.write(self.style.SUCCESS('Starting phone number migration...'))

        # Statistics
        stats = {
            'vendor': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'milkman': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
            'customer': {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0},
        }

        # Migrate vendors
        self.stdout.write('\n--- Migrating Vendor phone numbers ---')
        stats['vendor'] = self.migrate_vendors(dry_run)

        # Migrate milkmen
        self.stdout.write('\n--- Migrating Milkman phone numbers ---')
        stats['milkman'] = self.migrate_milkmen(dry_run)

        # Migrate customers
        self.stdout.write('\n--- Migrating Customer phone numbers ---')
        stats['customer'] = self.migrate_customers(dry_run)

        # Print summary
        self.print_summary(stats, dry_run)

    def migrate_vendors(self, dry_run):
        """Migrate vendor phone numbers from contact_id column"""
        VendorBusinessRegistration = apps.get_model('BusinessRegistration', 'VendorBusinessRegistration')
        stats = {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0}

        vendors = VendorBusinessRegistration.objects.all()
        stats['total'] = vendors.count()

        for vendor in vendors:
            try:
                # Get the raw phone number from the database column
                # The contact_id column currently contains the phone number as a string
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT contact_id FROM businessregistration_vendorbusinessregistration WHERE id = %s",
                        [vendor.id]
                    )
                    row = cursor.fetchone()
                    original_phone_number = row[0] if row else None

                if not original_phone_number:
                    self.stdout.write(f"  Skipping vendor {vendor.id} - no phone number in contact_id column")
                    stats['skipped'] += 1
                    continue

                # Check if contact_id is already a valid integer (already migrated)
                try:
                    contact_id_int = int(original_phone_number)
                    if contact_id_int < 1000000000:  # If it's a small number, likely already an ID
                        self.stdout.write(f"  Skipping vendor {vendor.id} - contact_id appears to be already migrated ({contact_id_int})")
                        stats['skipped'] += 1
                        continue
                except (ValueError, TypeError):
                    pass

                if not dry_run:
                    with transaction.atomic():
                        # Create or get the UniquePhoneNumber entry
                        obj, created = UniquePhoneNumber.objects.get_or_create(
                            phone_number=str(original_phone_number),
                            defaults={
                                'user_type': 'vendor',
                                'user_id': vendor.id
                            }
                        )

                        # Update the contact_id to the UniquePhoneNumber ID
                        with connection.cursor() as update_cursor:
                            update_cursor.execute(
                                "UPDATE businessregistration_vendorbusinessregistration SET contact_id = %s WHERE id = %s",
                                [obj.id, vendor.id]
                            )

                        if created:
                            self.stdout.write(
                                self.style.SUCCESS(f"  Migrated vendor {vendor.id}: {original_phone_number} -> UniquePhoneNumber ID {obj.id}")
                            )
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(f"  Updated vendor {vendor.id} with existing phone number: {original_phone_number} -> UniquePhoneNumber ID {obj.id}")
                            )
                else:
                    self.stdout.write(f"  Would migrate vendor {vendor.id}: {original_phone_number}")

                stats['migrated'] += 1

            except Exception as e:
                error_message = f"Error migrating vendor {vendor.id}: {str(e)}"
                self.stdout.write(self.style.ERROR(f"  {error_message}"))
                logger.error(error_message)
                logger.error(traceback.format_exc())
                stats['errors'] += 1

        return stats

    def migrate_milkmen(self, dry_run):
        """Migrate milkman phone numbers from phone_number column"""
        Milkman = apps.get_model('Milkman', 'Milkman')
        stats = {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0}

        milkmen = Milkman.objects.all()
        stats['total'] = milkmen.count()

        for milkman in milkmen:
            try:
                # Get the raw phone number from the database column
                # The phone_number column currently contains the phone number as a string
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT phone_number, phone_number_id FROM milkman_milkman WHERE id = %s",
                        [milkman.id]
                    )
                    row = cursor.fetchone()
                    original_phone_number = row[0] if row else None
                    current_phone_number_id = row[1] if row and len(row) > 1 else None

                # Skip if phone_number_id is already set (already migrated)
                if current_phone_number_id is not None:
                    self.stdout.write(f"  Skipping milkman {milkman.id} - already migrated (phone_number_id={current_phone_number_id})")
                    stats['skipped'] += 1
                    continue

                if not original_phone_number:
                    self.stdout.write(f"  Skipping milkman {milkman.id} - no phone number in phone_number column")
                    stats['skipped'] += 1
                    continue

                if not dry_run:
                    with transaction.atomic():
                        # Create or get the UniquePhoneNumber entry
                        obj, created = UniquePhoneNumber.objects.get_or_create(
                            phone_number=str(original_phone_number),
                            defaults={
                                'user_type': 'milkman',
                                'user_id': milkman.id
                            }
                        )

                        # Set phone_number_id and clear the old phone_number column
                        with connection.cursor() as update_cursor:
                            update_cursor.execute(
                                "UPDATE milkman_milkman SET phone_number_id = %s, phone_number = NULL WHERE id = %s",
                                [obj.id, milkman.id]
                            )

                        if created:
                            self.stdout.write(
                                self.style.SUCCESS(f"  Migrated milkman {milkman.id}: {original_phone_number} -> UniquePhoneNumber ID {obj.id}")
                            )
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(f"  Updated milkman {milkman.id} with existing phone number: {original_phone_number} -> UniquePhoneNumber ID {obj.id}")
                            )
                else:
                    self.stdout.write(f"  Would migrate milkman {milkman.id}: {original_phone_number}")

                stats['migrated'] += 1

            except Exception as e:
                error_message = f"Error migrating milkman {milkman.id}: {str(e)}"
                self.stdout.write(self.style.ERROR(f"  {error_message}"))
                logger.error(error_message)
                logger.error(traceback.format_exc())
                stats['errors'] += 1

        return stats

    def migrate_customers(self, dry_run):
        """Migrate customer phone numbers from contact column"""
        Customer = apps.get_model('Customer', 'Customer')
        stats = {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0}

        customers = Customer.objects.all()
        stats['total'] = customers.count()

        for customer in customers:
            try:
                # Get the raw phone number from the database column
                # The contact column currently contains the phone number as a string
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT contact, contact_id FROM customer_customer WHERE id = %s",
                        [customer.id]
                    )
                    row = cursor.fetchone()
                    original_phone_number = row[0] if row else None
                    current_contact_id = row[1] if row and len(row) > 1 else None

                # Skip if contact_id is already set (already migrated)
                if current_contact_id is not None:
                    self.stdout.write(f"  Skipping customer {customer.id} - already migrated (contact_id={current_contact_id})")
                    stats['skipped'] += 1
                    continue

                if not original_phone_number:
                    self.stdout.write(f"  Skipping customer {customer.id} - no phone number in contact column")
                    stats['skipped'] += 1
                    continue

                if not dry_run:
                    with transaction.atomic():
                        # Create or get the UniquePhoneNumber entry
                        obj, created = UniquePhoneNumber.objects.get_or_create(
                            phone_number=str(original_phone_number),
                            defaults={
                                'user_type': 'customer',
                                'user_id': customer.id
                            }
                        )

                        # Set contact_id and clear the old contact column
                        with connection.cursor() as update_cursor:
                            update_cursor.execute(
                                "UPDATE customer_customer SET contact_id = %s, contact = NULL WHERE id = %s",
                                [obj.id, customer.id]
                            )

                        if created:
                            self.stdout.write(
                                self.style.SUCCESS(f"  Migrated customer {customer.id}: {original_phone_number} -> UniquePhoneNumber ID {obj.id}")
                            )
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(f"  Updated customer {customer.id} with existing phone number: {original_phone_number} -> UniquePhoneNumber ID {obj.id}")
                            )
                else:
                    self.stdout.write(f"  Would migrate customer {customer.id}: {original_phone_number}")

                stats['migrated'] += 1

            except Exception as e:
                error_message = f"Error migrating customer {customer.id}: {str(e)}"
                self.stdout.write(self.style.ERROR(f"  {error_message}"))
                logger.error(error_message)
                logger.error(traceback.format_exc())
                stats['errors'] += 1

        return stats

    def print_summary(self, stats, dry_run):
        """Print migration summary"""
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('MIGRATION SUMMARY'))
        self.stdout.write('=' * 60)

        if dry_run:
            self.stdout.write(self.style.WARNING('(DRY RUN - No data was actually saved)'))

        for user_type, data in stats.items():
            self.stdout.write(f"\n{user_type.upper()}:")
            self.stdout.write(f"  Total: {data['total']}")
            self.stdout.write(f"  Migrated: {data['migrated']}")
            self.stdout.write(f"  Skipped: {data['skipped']}")
            if data['errors'] > 0:
                self.stdout.write(self.style.ERROR(f"  Errors: {data['errors']}"))
            else:
                self.stdout.write(f"  Errors: {data['errors']}")

        total_migrated = sum(d['migrated'] for d in stats.values())
        total_errors = sum(d['errors'] for d in stats.values())

        self.stdout.write('\n' + '=' * 60)
        if total_errors == 0:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully processed {total_migrated} phone numbers')
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'Processed {total_migrated} phone numbers with {total_errors} errors'
                )
            )
        self.stdout.write('=' * 60)
