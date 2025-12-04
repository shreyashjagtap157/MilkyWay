from django.core.management.base import BaseCommand
from django.db.models import Count
from Systemadmin.models import UniquePhoneNumber

class Command(BaseCommand):
    help = 'Detect and remove duplicate phone numbers from UniquePhoneNumber table.'

    def handle(self, *args, **options):
        self.stdout.write('Starting phone number deduplication...')

        duplicates = (
            UniquePhoneNumber.objects.values('phone_number')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )

        if not duplicates:
            self.stdout.write(self.style.SUCCESS('No duplicate phone numbers found.'))
            return

        self.stdout.write(f'Found {len(duplicates)} duplicate phone number(s).')

        for item in duplicates:
            phone_number = item['phone_number']
            self.stdout.write(f"Processing duplicate: {phone_number}")

            # Get all instances for this phone number, order by creation time
            instances = UniquePhoneNumber.objects.filter(phone_number=phone_number).order_by('created_at')
            first_instance = instances.first()
            self.stdout.write(f"  Keeping instance ID: {first_instance.id}")

            # Bulk delete all but the first instance
            to_delete = instances.exclude(id=first_instance.id)
            count = to_delete.count()
            if count > 0:
                self.stdout.write(f"  Deleting {count} duplicate instance(s)")
                to_delete.delete()

        self.stdout.write(self.style.SUCCESS('Deduplication complete.'))
