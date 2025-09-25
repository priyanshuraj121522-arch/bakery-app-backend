# bakery/management/commands/bootstrap_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from bakery.models import Outlet, Product, Batch, Sale

class Command(BaseCommand):
    help = "Create roles (owner, outlet_manager, cashier) with sensible permissions"

    def handle(self, *args, **kwargs):
        # Create groups
        owner, _ = Group.objects.get_or_create(name="owner")
        manager, _ = Group.objects.get_or_create(name="outlet_manager")
        cashier, _ = Group.objects.get_or_create(name="cashier")

        # Collect model permissions
        def perms_for(model, codenames):
            ct = ContentType.objects.get_for_model(model)
            out = []
            for code in codenames:
                try:
                    out.append(Permission.objects.get(content_type=ct, codename=code))
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Missing perm {code} for {model.__name__}"))
            return out

        # Django default CRUD codenames use: add_*, change_*, delete_*, view_*
        owner_perms = (
            perms_for(Outlet,  ["add_outlet","change_outlet","delete_outlet","view_outlet"]) +
            perms_for(Product, ["add_product","change_product","delete_product","view_product"]) +
            perms_for(Batch,   ["add_batch","change_batch","delete_batch","view_batch"]) +
            perms_for(Sale,    ["add_sale","change_sale","delete_sale","view_sale"])
        )
        owner.permissions.set(owner_perms)

        manager_perms = (
            perms_for(Product, ["view_product"]) +
            perms_for(Batch,   ["add_batch","change_batch","view_batch"]) +
            perms_for(Sale,    ["add_sale","change_sale","view_sale"])
        )
        manager.permissions.set(manager_perms)

        cashier_perms = (
            perms_for(Product, ["view_product"]) +
            perms_for(Sale,    ["add_sale","view_sale"])
        )
        cashier.permissions.set(cashier_perms)

        self.stdout.write(self.style.SUCCESS("Roles bootstrapped: owner, outlet_manager, cashier"))
