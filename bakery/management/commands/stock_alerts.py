from django.core.management.base import BaseCommand

from bakery.alerts import run_low_stock_alerts


class Command(BaseCommand):
    help = "Run low stock checks and send notifications"

    def handle(self, *args, **options):
        items = run_low_stock_alerts()
        if not items:
            self.stdout.write("No low stock items detected.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Sent alerts for {len(items)} item(s)."))
