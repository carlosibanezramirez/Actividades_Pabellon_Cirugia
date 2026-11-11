from django.urls import path
from . import views

urlpatterns = [
    path('buscar-pabellon/', views.reservation_search, name='reservation_search'),
    path('pabellones/estado-preparacion/', views.preparation_status, name='preparation_status'),
    path('ocupacion-semanal/<int:room_id>/dia/<str:day_string>/reservas/', views.day_reservations, name='day_reservations'),
    path('ocupacion-semanal/', views.weekly_summary, name='weekly_summary'),
    path('agenda-semanal/', views.weekly_agenda, name='weekly_agenda'),
    path('agenda-semanal/<int:room_id>/dia/<str:day_string>/', views.weekly_day, name='weekly_day'),
    path('agenda/', views.agenda, name='agenda'),
    path('reservas/<int:pk>/cancelar/', views.reservation_cancel, name='reservation_cancel'),
    path('reservas/<int:pk>/editar/', views.reservation_edit, name='reservation_edit'),
    path('reservas/<int:pk>/', views.reservation_detail, name='reservation_detail'),
    path('pabellones/', views.board, name='room_board'),
    path('panel/', views.dashboard, name='dashboard'),
    path('', views.interventions, name='interventions'),
    path('nueva/', views.create, name='create'),
    path('intervenciones/<int:pk>/', views.detail, name='detail'),
    path('intervenciones/<int:pk>/preoperatorio/<str:kind>/completar/', views.complete_preoperative, name='complete_preoperative'),
    path('intervenciones/<int:pk>/eventos/<int:stage>/registrar/', views.record, name='record'),
    path('intervenciones/<int:pk>/eventos/<int:event_id>/corregir/', views.correct, name='correct'),
]
