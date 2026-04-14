from django.urls import path
from . import views


urlpatterns = [
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("presencas/",views.presencas, name="presencas"),
    path('camera/', views.camera_page, name='camera_page'),
    path('camera_feed/', views.camera_feed, name='camera_feed'),
    path('administracao/', views.administracao, name='administracao'),
    path('lista_utilizadores/', views.lista_utilizadores, name='lista_utilizadores'),
    path('utilizador/novo/', views.adicionar_utilizador, name='adicionar_utilizador'),
    path('utilizador/<int:user_id>/editar/', views.editar_utilizador, name='editar_utilizador'),
    path('utilizador/<int:user_id>/eliminar/', views.eliminar_utilizador, name='eliminar_utilizador'),
    path('', views.home, name='home'),
]