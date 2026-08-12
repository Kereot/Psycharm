from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from articles.forms import CommentForm, RatingForm
from articles.models import Article
from common.constants import (
    ARTICLE_LIST_PAGE_SIZE,
    ARTICLE_PENDING_FORM_SESSION_KEY,
    FORM_SESSION_WRITE_RATE_LIMIT,
    FORM_SESSION_WRITE_RATE_LIMIT_WINDOW_SECONDS,
)
from common.rate_limit import is_rate_limited


def article_list(request):
    queryset = Article.objects.filter(is_published=True).select_related('author')
    paginator = Paginator(queryset, ARTICLE_LIST_PAGE_SIZE)
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
        # Ограничение по IP против флуд POST запросами.
        ip = request.META.get('REMOTE_ADDR', '')
        if not is_rate_limited(
            'article_pending_form', ip, FORM_SESSION_WRITE_RATE_LIMIT, FORM_SESSION_WRITE_RATE_LIMIT_WINDOW_SECONDS,
        ):
            kind = 'submit_comment' if 'submit_comment' in request.POST else 'submit_rating'
            request.session[ARTICLE_PENDING_FORM_SESSION_KEY] = {
                'slug': article.slug,
                'kind': kind,
                'data': request.POST.dict(),
            }
        return redirect_to_login(request.get_full_path())

    user_rating = None
    if request.user.is_authenticated:
        user_rating = article.ratings.filter(author=request.user).first()

    # Восстанавливает текст/оценку, сохранённые выше при редиректе анонима на логин.
    pending = request.session.pop(ARTICLE_PENDING_FORM_SESSION_KEY, None)
    if pending and pending['slug'] != article.slug:
        pending = None

    comment_initial = pending['data'] if pending and pending['kind'] == 'submit_comment' else None
    rating_initial = pending['data'] if pending and pending['kind'] == 'submit_rating' else None

    comment_form = CommentForm(initial=comment_initial)
    rating_form = RatingForm(initial=rating_initial, instance=user_rating)

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
