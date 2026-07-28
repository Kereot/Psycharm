from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from api.urls import v1_patterns
from users.forms import LoginForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(v1_patterns)),
    path(
        'accounts/login/',
        auth_views.LoginView.as_view(template_name='registration/login.html', authentication_form=LoginForm),
        name='login',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('users.urls')),
    path('', include('pages.urls')),
    path('', include('articles.urls')),
    path('', include('consultations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
