from django.shortcuts import render

from articles.models import Article
from common.constants import HOME_RECENT_ARTICLES_COUNT
from pages.models import ServicePrice


def home(request):
    recent_articles = (
        Article.objects.filter(is_published=True)
        .select_related('author')
        .order_by('-created_at')[:HOME_RECENT_ARTICLES_COUNT]
    )
    return render(request, 'pages/home.html', {'recent_articles': recent_articles})


def about(request):
    return render(request, 'pages/about.html')


def contacts(request):
    return render(request, 'pages/contacts.html')


def prices(request):
    return render(request, 'pages/prices.html', {'prices': ServicePrice.objects.all()})
