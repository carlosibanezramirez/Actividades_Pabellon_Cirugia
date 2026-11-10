from django.urls import path
from . import views

urlpatterns = [
    path('pabellones/estado-preparacion/', views.preparation_status, name='preparation_status'),
    path('agenda-semanal/', views.weekly_agenda, name='weekly_agenda'),
    path('agenda-semanal/<int:room_id>/dia/<str:day_string>/', views.weekly_day, name='weekly_day'),
    path('agenda/', views.agenda, name='agenda'),
    path('reservas/<int:pk>/', views.reservation_detail, name='reservation_detail'),
    path('pabellones/', views.board, name='room_board'),
    path('panel/', views.dashboard, name='dashboard'),
    path('', views.interventions, name='interventions'),
    path('nueva/', views.create, name='create'),
    path('intervenciones/<int:pk>/', views.detail, name='detail'),
    path('intervenciones/<int:pk>/eventos/<int:stage>/registrar/', views.record, name='record'),
    path('intervenciones/<int:pk>/eventos/<int:event_id>/corregir/', views.correct, name='correct'),
]
