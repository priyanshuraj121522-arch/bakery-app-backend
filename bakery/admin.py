# bakery/admin.py
from django.contrib import admin
from .models import (
    Outlet, Ingredient, Product, Recipe, RecipeItem,
    Batch, Dispatch, DispatchLine, Sale, SaleItem,
    Wastage, StockLedger, UserProfile
)

# ---- Add search_fields for Outlet so it can be used in autocomplete_fields ----
@admin.register(Outlet)
class OutletAdmin(admin.ModelAdmin):
    search_fields = ("name",)          # <- required for autocomplete_fields to work
    list_display = ("id", "name", "address")
    ordering = ("id",)

# ---- UserProfile with autocomplete to User & Outlet ----
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "outlet")
    search_fields = ("user__username", "user__email", "outlet__name")  # makes this list searchable too
    autocomplete_fields = ["user", "outlet"]                           # now valid because Outlet has search_fields

# ---- Register the rest normally ----
rest_models = [
    Ingredient, Product, Recipe, RecipeItem,
    Batch, Dispatch, DispatchLine, Sale, SaleItem,
    Wastage, StockLedger
]
for m in rest_models:
    admin.site.register(m)
