from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create demo subscriptions: 3 monthly, 3 semiannual, 3 annual"

    def handle(self, *args, **options):
        from subscription.models import subscriptionPlan, SubscribedCustomer
        from Customer.models import Customer

        # mapping: name -> duration (matches SubscriptionPlan.PLAN_CHOICES)
        plan_map = {
            "monthly": 30,
            "semiannual": 180,
            "annual": 365,
        }

        # Ensure plans exist
        plans = {}
        for name, duration in plan_map.items():
            plan, _ = SubscriptionPlan.objects.get_or_create(
                duration=duration,
                defaults={
                    "plan_name": name.capitalize(),
                    "price": 0.00,
                    "description": f"{name.capitalize()} demo plan",
                },
            )
            plans[name] = plan

        # Fetch up to 9 customers (ordered by id)
        customers = list(Customer.objects.order_by("id")[:9])
        if not customers:
            self.stdout.write(self.style.WARNING("No customers found in database."))
            return

        # Assign three customers to each plan in order
        created = 0
        idx = 0
        for name in ("monthly", "semiannual", "annual"):
            plan = plans[name]
            for _ in range(3):
                if idx >= len(customers):
                    break
                cust = customers[idx]
                # field name is 'Customer' (capital C) in model definition
                sub_kwargs = {"Customer": cust, "plan": plan}
                # Create or get subscription without passing unknown default fields
                try:
                    sub, was_created = SubscribedCustomer.objects.get_or_create(**sub_kwargs)
                except TypeError:
                    # fallback: construct instance directly if get_or_create signature mismatch
                    sub = SubscribedCustomer(**sub_kwargs)
                    sub.save()
                    was_created = True

                # If the model defines 'is_active', ensure it's True for created records
                if was_created:
                    created += 1
                    if hasattr(sub, "is_active"):
                        try:
                            # set and save only the field if it exists
                            sub.is_active = True
                            sub.save(update_fields=["is_active"])
                        except Exception:
                            # if update_fields not supported, do a full save
                            sub.save()
                    self.stdout.write(self.style.SUCCESS(f"Created subscription: customer={cust.id} plan={name}"))
                else:
                    # subscription already exists
                    self.stdout.write(self.style.NOTICE(f"Subscription exists: customer={cust.id} plan={name}"))
                idx += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Subscriptions created: {created}"))
