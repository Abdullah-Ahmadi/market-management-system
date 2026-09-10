from decimal import Decimal
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


def copy_product_prices(apps, schema_editor):
    Product = apps.get_model('core', 'Product')
    for product in Product.objects.all():
        product.wholesale_price = product.default_price
        product.retail_price = product.default_price
        product.save(update_fields=['wholesale_price', 'retail_price'])


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='zone',
            name='supervisor',
            field=models.ForeignKey(
                limit_choices_to={'role__code': 'SUPERVISOR'},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='supervised_zones',
                to='core.user',
            ),
        ),
        migrations.CreateModel(
            name='ProductSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('singleton', models.PositiveSmallIntegerField(default=1, editable=False, unique=True)),
                ('value', models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.AddField(
            model_name='product',
            name='size',
            field=models.CharField(default='Standard', help_text='Examples: 330 ml, 500 ml, 1.5 L', max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='product',
            name='wholesale_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0'))]),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='product',
            name='retail_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0'))]),
            preserve_default=False,
        ),
        migrations.RunPython(copy_product_prices, migrations.RunPython.noop),
        migrations.RemoveField(model_name='product', name='default_price'),
        migrations.AlterField(
            model_name='product',
            name='product_code',
            field=models.CharField(editable=False, max_length=30, unique=True),
        ),
        migrations.AlterField(
            model_name='product',
            name='unit',
            field=models.CharField(default='carton', max_length=40),
        ),
        migrations.AlterModelOptions(
            name='product',
            options={'ordering': ['name', 'size']},
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='company_short_name',
            field=models.CharField(default='MMS', max_length=40),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='company_tagline',
            field=models.CharField(blank=True, default='Market Management System', max_length=180),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='allow_general_sales',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='allow_salesman_discounts',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='default_page_size',
            field=models.PositiveSmallIntegerField(default=50, validators=[django.core.validators.MinValueValidator(10), django.core.validators.MaxValueValidator(200)]),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='default_report_range_days',
            field=models.PositiveSmallIntegerField(default=30, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(366)]),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='dashboard_trend_days',
            field=models.PositiveSmallIntegerField(default=7, validators=[django.core.validators.MinValueValidator(3), django.core.validators.MaxValueValidator(31)]),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='customer_search_limit',
            field=models.PositiveSmallIntegerField(default=20, validators=[django.core.validators.MinValueValidator(5), django.core.validators.MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='session_timeout_minutes',
            field=models.PositiveSmallIntegerField(default=480, validators=[django.core.validators.MinValueValidator(5), django.core.validators.MaxValueValidator(1440)]),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='support_phone',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='support_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='systemsetting',
            name='help_message',
            field=models.TextField(blank=True, default='If you need help that is not covered on this page, contact your supervisor or system administrator.'),
        ),
    ]
