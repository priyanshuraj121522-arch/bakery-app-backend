from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os

class Command(BaseCommand):
    help = "Create a superuser from env vars if it doesn't exist"

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "admin").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "admin")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()

        if not username or not password:
            self.stdout.write(self.style.ERROR("Missing username or password"))
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING("Superuser already exists"))
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created"))
