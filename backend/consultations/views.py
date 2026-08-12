from django.contrib import messages
from django.db import IntegrityError
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render

from common.constants import CONSULTATION_STATUS_CLOSED, STAFF_PANEL_PAGE_SIZE
from consultations.forms import ConsultationForm
from consultations.models import Consultation
from consultations.services import remember_anonymous_consultation


def consultation_request(request):
    if request.method == 'POST':
        form = ConsultationForm(request.POST)
        if form.is_valid():
            consultation = form.save(commit=False)
            user = request.user if request.user.is_authenticated else None
            consultation.user = user

            existing_by_contact = Consultation.objects.filter(
                contact_method=consultation.contact_method,
                contact_value=consultation.contact_value,
            ).exclude(status=CONSULTATION_STATUS_CLOSED).exists()

            was_created = False
            if not existing_by_contact:
                try:
                    consultation.save()
                    was_created = True
                except IntegrityError:
                    pass

            if was_created and user is None:
                remember_anonymous_consultation(request, consultation)

            if user is not None:
                other_open = Consultation.objects.filter(user=user).exclude(status=CONSULTATION_STATUS_CLOSED)
                if was_created:
                    other_open = other_open.exclude(pk=consultation.pk)
                existing_for_user = other_open.order_by('-created_at').first()
                if existing_for_user is not None:
                    messages.info(
                        request,
                        f'У вас уже есть заявка в статусе «{existing_for_user.get_status_display()}» '
                        f'от {existing_for_user.created_at:%d.%m.%Y}.',
                    )

            return redirect('consultations:success')
    else:
        form = ConsultationForm()

    return render(request, 'consultations/request_form.html', {'form': form})


def consultation_success(request):
    return render(request, 'consultations/success.html')


def staff_panel(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        raise Http404

    # cookie csrftoken
    get_token(request)
    return render(request, 'consultations/staff_panel.html', {'page_size': STAFF_PANEL_PAGE_SIZE})
