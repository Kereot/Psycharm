from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from articles.forms import CommentForm, RatingForm
from articles.models import Article
from common.constants import API_PAGE_SIZE


def article_list(request):
    queryset = Article.objects.filter(is_published=True).select_related('author')
    paginator = Paginator(queryset, API_PAGE_SIZE)
    try:
        page_obj = paginator.page(request.GET.get('page') or 1)
    except (PageNotAnInteger, EmptyPage):
        raise Http404('Такой страницы нет.')

    context = {
        'articles': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
    }
    return render(request, 'articles/article_list.html', context)


def _save_relation(request, article, form):
    if not form.is_valid():
        return False
    obj = form.save(commit=False)
    obj.article = article
    obj.author = request.user
    obj.save()
    return True


def article_detail(request, slug):
    article = get_object_or_404(
        Article.objects.filter(is_published=True).select_related('author'),
        slug=slug,
    )

    if request.method == 'POST' and not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    user_rating = None
    if request.user.is_authenticated:
        user_rating = article.ratings.filter(author=request.user).first()

    comment_form = CommentForm()
    rating_form = RatingForm(instance=user_rating)

    if request.method == 'POST' and 'submit_comment' in request.POST:
        comment_form = CommentForm(request.POST)
        if _save_relation(request, article, comment_form):
            messages.success(request, 'Комментарий добавлен.')
            return redirect('articles:detail', slug=article.slug)

    elif request.method == 'POST' and 'submit_rating' in request.POST:
        rating_form = RatingForm(request.POST, instance=user_rating)
        if _save_relation(request, article, rating_form):
            messages.success(request, 'Спасибо за оценку!')
            return redirect('articles:detail', slug=article.slug)

    context = {
        'article': article,
        'comments': article.comments.select_related('author'),
        'comment_form': comment_form,
        'rating_form': rating_form,
        'user_rating': user_rating,
        'average_rating': article.ratings.aggregate(average=Avg('value'))['average'],
        'ratings_count': article.ratings.count(),
    }
    return render(request, 'articles/article_detail.html', context)
