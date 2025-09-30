from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bakery", "0005_product_reorder_threshold"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(choices=[("create", "Create"), ("update", "Update"), ("delete", "Delete")], max_length=50),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="row_id",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="table",
            field=models.CharField(max_length=100),
        ),
    ]
