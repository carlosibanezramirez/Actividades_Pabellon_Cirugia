from django.contrib import admin
from .models import Correction, Doctor, Event, Intervention, Procedure, Room


@admin.register(Room, Procedure)
class CatalogAdmin(admin.ModelAdmin):
    list_display = ['name', 'active']
    list_filter = ['active']
    search_fields = ['name']


@admin.register(Doctor)
class DoctorAdmin(CatalogAdmin):
    list_display = ['name', 'specialty', 'active']
    list_filter = ['active', 'specialty']
    search_fields = ['name', 'specialty']


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Intervention)
class InterventionAdmin(ReadOnlyAdmin):
    list_display = ['id', 'room', 'procedure', 'doctor', 'created_at', 'completed_at']
    list_filter = ['room']


@admin.register(Event)
class EventAdmin(ReadOnlyAdmin):
    list_display = ['intervention', 'stage', 'occurred_at', 'original_at', 'recorded_by']


@admin.register(Correction)
class CorrectionAdmin(ReadOnlyAdmin):
    list_display = ['event', 'previous_at', 'new_at', 'reason', 'corrected_by', 'corrected_at']
