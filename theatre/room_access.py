from django.core.exceptions import ValidationError

from .models import Room


def can_reserve_room(user, room):
    if not room.active:
        return False
    if room.room_type != Room.Type.EMERGENCY:
        return True
    return bool(user and user.is_authenticated and user.is_active and (
        user.is_superuser or user.groups.filter(name='Administrador').exists()
    ))


def require_room_booking_access(user, room):
    if not can_reserve_room(user, room):
        raise ValidationError('Solo el perfil Administrador puede generar o trasladar reservas en un pabellón de Urgencias.')
