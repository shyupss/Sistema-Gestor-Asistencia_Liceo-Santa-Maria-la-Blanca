"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from inicio import views as inicio_views
from academico import views as academico_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', inicio_views.pagina_principal, name='home'), # <-- El '' (string vacío) es lo que oculta el cohete
    path('segunda/', inicio_views.pagina_segunda, name='nothome'),
    path('alumnos/', academico_views.pagina_alumnos, name = 'alumnos'),
    path('cursos/', academico_views.pagina_cursos, name= 'cursos'),
]
