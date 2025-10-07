from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bakery", "0011_cogsentry_purchasebatch"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="sale",
            index=models.Index(fields=["billed_at"], name="sale_billed_at_idx"),
        ),
        migrations.AddIndex(
            model_name="sale",
            index=models.Index(fields=["outlet", "billed_at"], name="sale_outlet_billed_idx"),
        ),
        migrations.AddIndex(
            model_name="saleitem",
            index=models.Index(fields=["sale"], name="saleitem_sale_idx"),
        ),
        migrations.AddIndex(
            model_name="saleitem",
            index=models.Index(fields=["product"], name="saleitem_product_idx"),
        ),
        migrations.AddIndex(
            model_name="stockledger",
            index=models.Index(fields=["batch"], name="stockledger_batch_idx"),
        ),
    ]
