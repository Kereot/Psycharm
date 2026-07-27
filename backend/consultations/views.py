from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render

from common.constants import DUPLICATE_CONSULTATION_MESSAGE
from common.exceptions import NotificationDeliveryError
from consultations.forms import ConsultationForm


def consultation_request(request):
    if request.method == 'POST':
        form = ConsultationForm(request.POST)
        if form.is_valid():
            consultation = form.save(commit=False)
            consultation.user = request.user if request.user.is_authenticated else None
            try:
                with transaction.atomic():
                    consultation.save()
            except IntegrityError:
                form.add_error(None, DUPLICATE_CONSULTATION_MESSAGE)
            except NotificationDeliveryError:
                return redirect('consultations:contacts')
            else:
                return redirect('consultations:success')
    else:
        form = ConsultationForm()

    return render(request, 'consultations/request_form.html', {'form': form})


def consultation_success(request):
    return render(request, 'consultations/success.html')


def consultation_contacts(request):
    return render(request, 'consultations/contacts.html', {
        'contact_email': settings.ADMIN_NOTIFICATION_EMAIL,
    })


def staff_panel(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        raise Http404

    # cookie csrftoken
    get_token(request)
    return render(request, 'consultations/staff_panel.html')
