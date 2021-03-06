# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('badges', '0003_schema__add_event_configuration'),
    ]

    operations = [
        migrations.AddField(
            model_name='badgeclass',
            name='badgr_server_slug',
            field=models.SlugField(default=b'', max_length=255),
        ),
        migrations.AddField(
            model_name='badgeassertion',
            name='badgr_server_slug',
            field=models.SlugField(default=b'', max_length=255),
        ),
        migrations.AddField(
            model_name='badgeassertion',
            name='image_url',
            field=models.URLField(null=True),
        )
    ]
