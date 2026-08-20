import time

from common.constants import CONSULTATION_SESSION_CLAIM_KEY, CONSULTATION_SESSION_CLAIM_TTL_SECONDS
from consultations.models import Consultation


def remember_anonymous_consultation(request, consultation):
    """Запоминает в сессии браузера (id, время) только что созданной анонимной заявки."""
    entries = request.session.get(CONSULTATION_SESSION_CLAIM_KEY, [])
    entries.append([consultation.pk, time.time()])
    request.session[CONSULTATION_SESSION_CLAIM_KEY] = entries


def claim_session_consultations(request, user):
    """Связывает с user анонимные заявки, оставленные в этой же сессии до входа/регистрации."""
    entries = request.session.pop(CONSULTATION_SESSION_CLAIM_KEY, [])
    if not entries:
        return 0

    now = time.time()
    fresh_ids = [
        consultation_id for consultation_id, remembered_at in entries
        if now - remembered_at < CONSULTATION_SESSION_CLAIM_TTL_SECONDS
    ]
    if not fresh_ids:
        return 0

    return Consultation.objects.filter(id__in=fresh_ids, user__isnull=True).update(user=user)
