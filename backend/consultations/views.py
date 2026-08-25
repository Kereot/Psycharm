from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render

from common.constants import (
    CONSULTATION_CREATE_UPDATE_RATE_LIMIT,
    CONSULTATION_CREATE_UPDATE_RATE_LIMIT_WINDOW_SECONDS,
    CONSULTATION_STATUS_CLOSED,
    STAFF_PANEL_PAGE_SIZE,
)
from common.rate_limit import is_rate_limited
from consultations.forms import ConsultationEditForm, ConsultationForm
from consultations.models import Consultation
from consultations.services import remember_anonymous_consultation
from consultations.signals import dispatch_consultation_update_notification


def consultation_request(request):
    if request.method != 'POST':
        return render(request, 'consultations/request_form.html', {'form': ConsultationForm()})

    form = ConsultationForm(request.POST)
    if not form.is_valid():
        return render(request, 'consultations/request_form.html', {'form': form})

    user = request.user if request.user.is_authenticated else None
    # Отправитель - IP для анонима, пользователь для авторизованного, а не контактные данные из формы.
    sender_id = str(user.pk) if user is not None else request.META.get('REMOTE_ADDR', '')
    # Лимит — только на реально валидные отправки.
    if is_rate_limited(
        'consultation_create', sender_id,
        CONSULTATION_CREATE_UPDATE_RATE_LIMIT, CONSULTATION_CREATE_UPDATE_RATE_LIMIT_WINDOW_SECONDS,
    ):
        messages.error(request, 'Слишком много заявок. Попробуйте позже.')
        return render(request, 'consultations/request_form.html', {'form': form}, status=429)

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


@login_required
def my_consultations(request):
    consultations = Consultation.objects.filter(user=request.user)
    return render(request, 'consultations/my_consultations.html', {'consultations': consultations})


@login_required
def my_consultation_edit(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk, user=request.user)
    if not consultation.is_editable_by_owner:
        raise Http404

    if request.method != 'POST':
        form = ConsultationEditForm(instance=consultation)
        return render(request, 'consultations/my_consultation_edit.html', {'form': form, 'consultation': consultation})

    old_contact_method = consultation.contact_method
    old_contact_value = consultation.contact_value
    old_message = consultation.message

    form = ConsultationEditForm(request.POST, instance=consultation)
    if not form.is_valid():
        return render(request, 'consultations/my_consultation_edit.html', {'form': form, 'consultation': consultation})

    if not form.has_changed():
        messages.info(request, 'Изменений не было.')
        return redirect('consultations:my')

    # Лимит - только на реальные изменения: невалидные попытки и повтор без изменений не тратят квоту впустую.
    if is_rate_limited(
        'consultation_edit', str(request.user.pk),
        CONSULTATION_CREATE_UPDATE_RATE_LIMIT, CONSULTATION_CREATE_UPDATE_RATE_LIMIT_WINDOW_SECONDS,
    ):
        messages.error(request, 'Слишком много изменений. Попробуйте позже.')
        return redirect('consultations:my')

    consultation = form.save()
    dispatch_consultation_update_notification(consultation, old_contact_method, old_contact_value, old_message)
    messages.success(request, 'Заявка обновлена.')

    return redirect('consultations:my')


def staff_panel(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        raise Http404

    # cookie csrftoken
    get_token(request)
    return render(request, 'consultations/staff_panel.html', {'page_size': STAFF_PANEL_PAGE_SIZE})
