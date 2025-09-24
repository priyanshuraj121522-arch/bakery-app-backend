from django.contrib import admin
from .models import (Outlet, Ingredient, Product, Recipe, RecipeItem,
                     Batch, Dispatch, DispatchLine, Sale, SaleItem, Wastage, StockLedger)

models = [Outlet, Ingredient, Product, Recipe, RecipeItem,
          Batch, Dispatch, DispatchLine, Sale, SaleItem, Wastage, StockLedger]
for m in models:
    admin.site.register(m)
