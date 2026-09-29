from django.db import migrations


def ensure_legacy_members(apps, schema_editor):
    # A fresh VPS has never run the desktop schema creator. Never replace existing data.
    if 'users' not in schema_editor.connection.introspection.table_names():
        schema_editor.create_model(apps.get_model('members', 'LegacyMember'))


class Migration(migrations.Migration):
    dependencies = [('members', '0006_gymsynccursor_gymsyncrecord')]
    operations = [migrations.RunPython(ensure_legacy_members, migrations.RunPython.noop)]
