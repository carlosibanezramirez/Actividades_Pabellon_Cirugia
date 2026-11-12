"""Acceso operativo acotado al médico responsable, sin conceder permisos globales."""
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import Http404
from .models import Doctor


def linked_doctor(user):
    if user.is_authenticated and user.has_perm('theatre.view_own_agenda'):
        return Doctor.objects.filter(user=user, active=True).first()
    return None


def require_medical_access(user, doctor_id=None):
    doctor = linked_doctor(user)
    if doctor:
        if doctor_id is not None and doctor.pk != doctor_id:
            raise Http404
        return doctor
    if not user.is_active or not user.has_perm('theatre.operate_intervention'):
        raise PermissionDenied
    return None


def medical_access(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        require_medical_access(request.user)
        return view(request, *args, **kwargs)
    return wrapped


def owned(queryset, user):
    doctor = require_medical_access(user)
    return queryset.filter(doctor=doctor) if doctor else queryset
