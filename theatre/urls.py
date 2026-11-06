from django.urls import path
from . import views

urlpatterns = [
    path('pabellones/', views.board, name='room_board'),
    path('panel/', views.dashboard, name='dashboard'),
    path('', views.interventions, name='interventions'),
    path('nueva/', views.create, name='create'),
    path('intervenciones/<int:pk>/', views.detail, name='detail'),
    path('intervenciones/<int:pk>/eventos/<int:stage>/registrar/', views.record, name='record'),
    path('intervenciones/<int:pk>/eventos/<int:event_id>/corregir/', views.correct, name='correct'),
]
