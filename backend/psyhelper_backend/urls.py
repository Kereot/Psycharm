from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from api.urls import v1_patterns
from users.forms import PasswordResetForm, SetPasswordForm
from users.views import LoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(v1_patterns)),
    path('accounts/login/', LoginView.as_view(), name='login'),
    # Переопределены только ради своих form_class (стилизация Bootstrap).
    path(
        'accounts/password_reset/',
        auth_views.PasswordResetView.as_view(form_class=PasswordResetForm),
        name='password_reset',
    ),
    path(
        'accounts/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(form_class=SetPasswordForm),
        name='password_reset_confirm',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('users.urls')),
    path('', include('pages.urls')),
    path('', include('articles.urls')),
    path('', include('consultations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
