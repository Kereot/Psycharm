import string

from faker import Faker

from common.constants import CONTACT_METHOD_EMAIL, CONTACT_METHOD_TELEGRAM

FAKE_TAG = 'faked'

_faker = Faker()


def contact_value_faker(contact_method):
    """Случайный контакт под выбранный способ связи."""
    if contact_method == CONTACT_METHOD_TELEGRAM:
        return f'@{_faker.lexify("?????", letters=string.ascii_lowercase)}_{FAKE_TAG}'
    if contact_method == CONTACT_METHOD_EMAIL:
        return f'{FAKE_TAG}_{_faker.safe_email()}'
    return _faker.numerify('+7000#######')


# Обе функции меняют form.instance, а не атрибуты формы.
# Подменяются только поля, которые пользователь реально ввёл (form.changed_data): уже
# подменённые значения при повторном сохранении формы не перегенерируются.

def user_names_faker(form):
    if 'first_name' in form.changed_data:
        form.instance.first_name = f'{_faker.first_name()}_{FAKE_TAG}'
    if 'last_name' in form.changed_data:
        form.instance.last_name = f'{_faker.last_name()}_{FAKE_TAG}'


def applicant_names_faker(form):
    if 'name' in form.changed_data:
        form.instance.name = f'{_faker.first_name()} {_faker.last_name()}_{FAKE_TAG}'
    if 'contact_value' in form.changed_data:
        form.instance.contact_value = contact_value_faker(form.instance.contact_method)
