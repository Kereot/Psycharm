from django.urls import path

from pages import views

app_name = 'pages'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contacts/', views.contacts, name='contacts'),
    path('prices/', views.prices, name='prices'),
    path('privacy/', views.privacy, name='privacy'),
]
