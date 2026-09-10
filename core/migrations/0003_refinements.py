import django.core.validators
from django.db import migrations, models

import core.models


class Migration(migrations.Migration):
    dependencies = [('core', '0002_enhanced_mms')]

    operations = [
        migrations.AddField(
            model_name='systemsetting',
            name='company_logo',
            field=models.FileField(
                blank=True,
                help_text='PNG, JPG/JPEG or WebP; maximum 3 MB.',
                null=True,
                upload_to='branding/',
                validators=[
                    django.core.validators.FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp']),
                    core.models.validate_company_logo_size,
                ],
            ),
        ),
    ]
