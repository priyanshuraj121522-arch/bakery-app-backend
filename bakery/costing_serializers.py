# COGS START
from rest_framework import serializers

from .models import Ingredient, Recipe, RecipeItem


class IngredientReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ("id", "name", "uom", "unit_cost", "active")
        read_only_fields = fields


class RecipeItemReadSerializer(serializers.ModelSerializer):
    ingredient = IngredientReadSerializer(read_only=True)

    class Meta:
        model = RecipeItem
        fields = ("id", "ingredient", "qty_per_unit", "wastage_pct")
        read_only_fields = fields


class RecipeReadSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    items = RecipeItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = Recipe
        fields = ("id", "product", "items")
        read_only_fields = fields

    def get_product(self, obj):
        product = getattr(obj, "product", None)
        if not product:
            return None
        return {
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
        }
# COGS END
