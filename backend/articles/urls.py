from django.urls import path

from articles import views

app_name = 'articles'

urlpatterns = [
    path('articles/', views.article_list, name='list'),
    path('articles/<slug:slug>/', views.article_detail, name='detail'),
]
