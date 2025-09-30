from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

ROLES = ["Owner", "Manager", "Cashier"]


class Command(BaseCommand):
    help = "Seed default roles/groups and ensure superusers are Owners."

    def handle(self, *args, **options):
        created_any = False
        for role in ROLES:
            group, created = Group.objects.get_or_create(name=role)
            if created:
                created_any = True
                self.stdout.write(self.style.SUCCESS(f"Created group: {role}"))
        if not created_any:
            self.stdout.write("Groups already exist.")

        owner_group = Group.objects.get(name="Owner")
        User = get_user_model()
        count = 0
        for user in User.objects.filter(is_superuser=True):
            if owner_group not in user.groups.all():
                user.groups.add(owner_group)
                count += 1
        self.stdout.write(f"Superusers linked to Owner group: {count}")
