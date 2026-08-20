from django.contrib import messages
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render

from common.constants import (
    CONSULTATION_CREATE_RATE_LIMIT,
    CONSULTATION_CREATE_RATE_LIMIT_WINDOW_SECONDS,
    CONSULTATION_STATUS_CLOSED,
    STAFF_PANEL_PAGE_SIZE,
)
from common.rate_limit import is_rate_limited
from consultations.forms import ConsultationForm
from consultations.models import Consultation
from consultations.services import remember_anonymous_consultation


def consultation_request(request):
    if request.method != 'POST':
        return render(request, 'consultations/request_form.html', {'form': ConsultationForm()})

    user = request.user if request.user.is_authenticated else None
    # Лимит — на отправителя (IP для анонима, пользователь для авторизованного), а не
    # на контактные данные из формы: раньше от флуда защищал заодно и UniqueConstraint
    # на (contact_method, contact_value), но это позволяло "застолбить" чужой контакт
    # мусорной заявкой — настоящая заявка с тем же контактом молча проваливалась.
    sender_id = str(user.pk) if user is not None else request.META.get('REMOTE_ADDR', '')
    if is_rate_limited(
        'consultation_create', sender_id, CONSULTATION_CREATE_RATE_LIMIT, CONSULTATION_CREATE_RATE_LIMIT_WINDOW_SECONDS,
    ):
        messages.error(request, 'Слишком много заявок. Попробуйте позже.')
        return render(request, 'consultations/request_form.html', {'form': ConsultationForm()}, status=429)

    form = ConsultationForm(request.POST)
    if not form.is_valid():
        return render(request, 'consultations/request_form.html', {'form': form})

    consultation = form.save(commit=False)
    consultation.user = user
    consultation.save()

    if user is None:
        remember_anonymous_consultation(request, consultation)
    else:
        existing_for_user = (
            Consultation.objects.filter(user=user)
            .exclude(status=CONSULTATION_STATUS_CLOSED)
            .exclude(pk=consultation.pk)
            .order_by('-created_at')
            .first()
        )
        if existing_for_user is not None:
            messages.info(
                request,
                f'У вас уже есть заявка в статусе «{existing_for_user.get_status_display()}» '
                f'от {existing_for_user.created_at:%d.%m.%Y}.',
            )

    return redirect('consultations:success')


def consultation_success(request):
    return render(request, 'consultations/success.html')


def staff_panel(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        raise Http404

    # cookie csrftoken
    get_token(request)
    return render(request, 'consultations/staff_panel.html', {'page_size': STAFF_PANEL_PAGE_SIZE})
