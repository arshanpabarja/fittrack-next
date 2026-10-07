from django.db import migrations


def seed(apps, schema_editor):
    Exercise = apps.get_model('members', 'Exercise')
    entries = [
        ('پرس سینه هالتر', 'chest', 'هالتر و نیمکت', 'پاها ثابت و کتف‌ها جمع؛ هالتر را با کنترل پایین بیاورید.', 'بلند شدن لگن یا رها کردن هالتر روی سینه'),
        ('پرس بالا سینه دمبل', 'chest', 'دمبل و نیمکت شیب‌دار', 'با مچ خنثی و دامنه کنترل‌شده اجرا کنید.', 'شیب بیش از حد نیمکت و قوس زیاد کمر'),
        ('لت سیم‌کش', 'back', 'دستگاه سیم‌کش', 'با تنه ثابت، آرنج‌ها را به سمت پایین حرکت دهید.', 'تاب دادن بدن برای جابه‌جایی وزنه'),
        ('نشر جانب دمبل', 'shoulders', 'دمبل', 'آرنج کمی خم؛ دست‌ها را تا ارتفاع شانه بالا ببرید.', 'بالا انداختن شانه‌ها و تاب دادن دمبل'),
        ('پشت بازو سیم‌کش', 'arms', 'دستگاه سیم‌کش', 'آرنج‌ها کنار بدن ثابت بمانند.', 'حرکت شانه و تنه به جای باز کردن آرنج'),
        ('اسکوات هالتر', 'legs', 'هالتر و رک', 'با تنه پایدار و زانوها در امتداد پنجه پایین بروید.', 'جمع شدن زانوها به داخل'),
        ('ددلیفت رومانیایی', 'legs', 'هالتر', 'لگن را عقب ببرید و هالتر را نزدیک پا نگه دارید.', 'گرد کردن کمر و خم کردن زیاد زانو'),
        ('پلانک', 'core', 'مت', 'تنه را در یک خط نگه دارید و تنفس را ادامه دهید.', 'افتادن لگن و حبس نفس'),
        ('بارفیکس', 'back', 'میله بارفیکس', 'با کتف فعال و بدون تاب، بدن را بالا بکشید.', 'تاب دادن بدن و کوتاه کردن دامنه'),
        ('گابلت اسکوات', 'full_body', 'دمبل یا کتل‌بل', 'وزنه را نزدیک سینه نگه دارید و با کنترل بنشینید.', 'خم شدن زیاد تنه و بلند شدن پاشنه'),
    ]
    for name, group, equipment, instructions, mistakes in entries:
        Exercise.objects.create(name=name, muscle_group=group, equipment=equipment,
                                instructions=instructions, common_mistakes=mistakes)


def unseed(apps, schema_editor):
    apps.get_model('members', 'Exercise').objects.filter(coach=None).delete()


class Migration(migrations.Migration):
    dependencies = [('members', '0011_coach_workspace')]
    operations = [migrations.RunPython(seed, unseed)]
