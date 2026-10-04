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


def changed_values(data, instance=None):
    """
    Поля из data, которые пользователь реально ввёл.
    Работает со словарями (validated_data сериализаторов, cleaned_data форм)
    и возвращает словарь подмен {поле: новое значение} - ничего не меняя само.
    """
    if instance is None:
        return dict(data)
    return {field: value for field, value in data.items() if getattr(instance, field, None) != value}


def fake_user_data(entered):
    fakes = {}
    if 'first_name' in entered:
        fakes['first_name'] = f'{_faker.first_name()}_{FAKE_TAG}'
    if 'last_name' in entered:
        fakes['last_name'] = f'{_faker.last_name()}_{FAKE_TAG}'
    return fakes


def fake_applicant_data(entered, contact_method):
    fakes = {}
    if 'name' in entered:
        fakes['name'] = f'{_faker.first_name()} {_faker.last_name()}_{FAKE_TAG}'
    if 'contact_value' in entered:
        fakes['contact_value'] = contact_value_faker(contact_method)
    return fakes


# Обёртки для форм сайта: меняют form.instance, а не атрибуты формы - save() берёт данные
# из instance (их туда кладёт is_valid()), поэтому вызывать надо после is_valid() и до save().

def _entered_by_form(form):
    return {field: form.cleaned_data[field] for field in form.changed_data}


def _apply(instance, fakes):
    for field, value in fakes.items():
        setattr(instance, field, value)


def user_names_faker(form):
    _apply(form.instance, fake_user_data(_entered_by_form(form)))


def applicant_names_faker(form):
    _apply(form.instance, fake_applicant_data(_entered_by_form(form), form.instance.contact_method))
