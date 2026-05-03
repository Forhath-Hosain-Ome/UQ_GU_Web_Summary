# Add format_type field to UploadBatch

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('final_summary', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='uploadbatch',
            name='format_type',
            field=models.CharField(
                choices=[
                    ('SPI',     'SPI Format (78)'),
                    ('REGULAR', 'Regular Format (35)'),
                    ('SWEATER', 'Sweater Format (37)'),
                ],
                default='SPI',
                max_length=20,
            ),
        ),
    ]
