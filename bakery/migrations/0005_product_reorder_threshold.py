from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bakery", "0004_auditlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="reorder_threshold",
            field=models.FloatField(default=0),
        ),
    ]
