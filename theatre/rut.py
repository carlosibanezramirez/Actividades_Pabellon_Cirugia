import re
from django.core.exceptions import ValidationError


def normalize_rut(value):
    compact = re.sub(r'[.\s-]', '', str(value or '')).upper()
    if not re.fullmatch(r'\d{1,8}[0-9K]', compact):
        raise ValidationError('Ingrese un RUT válido, por ejemplo 12.345.678-5.')
    body, digit = str(int(compact[:-1])), compact[-1]
    if body == '0':
        raise ValidationError('Ingrese un RUT válido.')
    total = sum(int(number) * (2 + index % 6) for index, number in enumerate(reversed(body)))
    check = 11 - total % 11
    expected = '0' if check == 11 else 'K' if check == 10 else str(check)
    if digit != expected:
        raise ValidationError('El dígito verificador del RUT no es válido.')
    return f'{body}-{digit}'
