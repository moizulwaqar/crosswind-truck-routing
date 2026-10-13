from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Trip",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin_label", models.CharField(blank=True, max_length=300)),
                ("destination_label", models.CharField(blank=True, max_length=300)),
                ("origin_lat", models.FloatField()),
                ("origin_lon", models.FloatField()),
                ("destination_lat", models.FloatField()),
                ("destination_lon", models.FloatField()),
                ("departure", models.DateTimeField()),
                ("load_lb", models.FloatField()),
                ("interval_miles", models.PositiveSmallIntegerField()),
                ("recommended_route_id", models.CharField(max_length=8)),
                ("plan", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
