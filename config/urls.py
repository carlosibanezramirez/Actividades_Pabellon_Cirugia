from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ingresar/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('salir/', auth_views.LogoutView.as_view(), name='logout'),
    path('clave/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change.html', success_url='/'), name='password_change'),
    path('', include('theatre.urls')),
]
admin.site.site_header = 'Surgeon · Administración'
admin.site.site_title = 'Surgeon'
