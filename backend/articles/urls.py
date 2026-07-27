from django.urls import path

from articles import views

app_name = 'articles'

urlpatterns = [
    path('', views.ArticleListView.as_view(), name='list'),
    path('articles/<slug:slug>/', views.article_detail, name='detail'),
]
