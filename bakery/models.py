from django.db import models

class Outlet(models.Model):
    KITCHEN = "kitchen"; OUTLET = "outlet"
    TYPE_CHOICES = [(KITCHEN, "Kitchen"), (OUTLET, "Outlet")]
    name = models.CharField(max_length=120, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=OUTLET)
    address = models.TextField(blank=True)
    def __str__(self): return f"{self.name} ({self.type})"

class Ingredient(models.Model):
    name = models.CharField(max_length=120, unique=True)
    uom  = models.CharField(max_length=20, default="kg")
    min_stock = models.FloatField(default=0)
    def __str__(self): return self.name

class Product(models.Model):
    name = models.CharField(max_length=120, unique=True)
    sku  = models.CharField(max_length=50, unique=True)
    mrp  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    shelf_life_hours = models.IntegerField(default=24)
    reorder_threshold = models.FloatField(default=0)
    active = models.BooleanField(default=True)
    def __str__(self): return f"{self.sku} - {self.name}"

class Recipe(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="recipe")
    yield_qty = models.FloatField(default=1)
    yield_uom = models.CharField(max_length=20, default="pcs")

class RecipeItem(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="items")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)
    qty_per_batch = models.FloatField()
    uom = models.CharField(max_length=20, default="kg")
    loss_pct = models.FloatField(default=0)

class Batch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT)  # usually kitchen
    produced_on = models.DateTimeField(auto_now_add=True)
    expiry_on = models.DateTimeField()
    produced_qty = models.FloatField(default=0)

class Dispatch(models.Model):
    from_outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="dispatch_from")
    to_outlet   = models.ForeignKey(Outlet, on_delete=models.PROTECT, related_name="dispatch_to")
    created_at  = models.DateTimeField(auto_now_add=True)
    status      = models.CharField(max_length=20, default="in_transit")

class DispatchLine(models.Model):
    dispatch = models.ForeignKey(Dispatch, on_delete=models.CASCADE, related_name="lines")
    product  = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch    = models.ForeignKey(Batch, on_delete=models.PROTECT)
    qty      = models.FloatField()

class Sale(models.Model):
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT)
    billed_at = models.DateTimeField(auto_now_add=True)
    subtotal  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_mode = models.CharField(max_length=20, default="UPI")

class SaleItem(models.Model):
    sale    = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    qty     = models.FloatField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

class Wastage(models.Model):
    outlet = models.ForeignKey(Outlet, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT)
    qty = models.FloatField()
    reason = models.CharField(max_length=120, default="expired")
    noted_at = models.DateTimeField(auto_now_add=True)

class StockLedger(models.Model):
    INGREDIENT="ingredient"; PRODUCT="product"
    item_type = models.CharField(max_length=20, choices=[(INGREDIENT,"Ingredient"),(PRODUCT,"Product")])
    item_id   = models.IntegerField()
    outlet    = models.ForeignKey(Outlet, on_delete=models.PROTECT)
    batch     = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT)
    qty_in    = models.FloatField(default=0)
    qty_out   = models.FloatField(default=0)
    reason    = models.CharField(max_length=50)   # production, sale, wastage, dispatch_in/out, grn
    ref_table = models.CharField(max_length=50)
    ref_id    = models.IntegerField()
    created_at= models.DateTimeField(auto_now_add=True)
# --- User ↔ Outlet link for access scoping ---
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE, related_name="profile")
    # Owner can be null (owner sees all outlets). For managers/cashiers set the outlet they belong to.
    outlet = models.ForeignKey(Outlet, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")

    def __str__(self):
        who = self.user.username
        where = self.outlet.name if self.outlet else "ALL (owner)"
        return f"{who} → {where}"

@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created and not hasattr(instance, "profile"):
        UserProfile.objects.create(user=instance)

from .models_audit import AuditLog
