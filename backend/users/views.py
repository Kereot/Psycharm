from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as BaseLoginView
from django.shortcuts import redirect, render
from rest_framework.status import HTTP_429_TOO_MANY_REQUESTS

from common.constants import LOGIN_RATE_LIMIT, LOGIN_RATE_LIMIT_WINDOW_SECONDS
from common.rate_limit import is_rate_limited
from common.request import get_client_ip
from consultations.services import claim_session_consultations
from users.forms import LoginForm, ProfileForm, RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('articles:list')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            claim_session_consultations(request, user)
            messages.success(request, 'Добро пожаловать!')
            return redirect('articles:list')
    else:
        form = RegistrationForm()

    return render(request, 'users/register.html', {'form': form})


class LoginView(BaseLoginView):
    template_name = 'registration/login.html'
    authentication_form = LoginForm

    def post(self, request, *args, **kwargs):
        # Здесь лимит именно на попытку (валидную или нет).
        ip = get_client_ip(request)
        if is_rate_limited('login', ip, LOGIN_RATE_LIMIT, LOGIN_RATE_LIMIT_WINDOW_SECONDS):
            messages.error(request, 'Слишком много попыток входа. Попробуйте позже.')
            context = self.get_context_data(form=self.get_form())
            return self.render_to_response(context, status=HTTP_429_TOO_MANY_REQUESTS)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        claim_session_consultations(self.request, self.request.user)
        return response


@login_required
def profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            if form.has_changed():
                form.save()
                messages.success(request, 'Профиль обновлён.')
            else:
                messages.info(request, 'Изменений не было.')
            return redirect('users:profile')
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'users/profile.html', {'form': form})
