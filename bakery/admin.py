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

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    search_fields = ("name",)

# ---- Register the rest normally ----
rest_models = [
    Ingredient, Recipe, RecipeItem,
    Batch, Dispatch, DispatchLine, Sale, SaleItem,
    Wastage, StockLedger
]
for m in rest_models:
    admin.site.register(m)

# COGS START
class RecipeItemInline(admin.TabularInline):
    model = RecipeItem
    fields = ("ingredient", "qty_per_unit", "wastage_pct")
    extra = 1


class IngredientCostingAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "uom", "unit_cost", "active")
    list_filter = ("active",)
    search_fields = ("name",)


class RecipeCostingAdmin(admin.ModelAdmin):
    list_display = ("id", "product")
    autocomplete_fields = ("product",)
    inlines = [RecipeItemInline]
    search_fields = ("product__name",)
    search_fields = ("product__name",)


class RecipeItemCostingAdmin(admin.ModelAdmin):
    list_display = ("id", "recipe", "ingredient", "qty_per_unit", "wastage_pct")
    autocomplete_fields = ("recipe", "ingredient")
    list_select_related = ("recipe", "ingredient")
    search_fields = ("recipe__product__name", "ingredient__name")


admin.site.unregister(Ingredient)
admin.site.unregister(Recipe)
admin.site.unregister(RecipeItem)
admin.site.register(Ingredient, IngredientCostingAdmin)
admin.site.register(Recipe, RecipeCostingAdmin)
admin.site.register(RecipeItem, RecipeItemCostingAdmin)
# COGS END
