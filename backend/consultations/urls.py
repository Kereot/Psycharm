from django.urls import path

from consultations import views

app_name = 'consultations'

urlpatterns = [
    path('consultation/', views.consultation_request, name='request'),
    path('consultation/success/', views.consultation_success, name='success'),
    path('consultation/my/', views.my_consultations, name='my'),
    path('consultation/my/<int:pk>/edit/', views.my_consultation_edit, name='my_edit'),
    path('consultation/staff/', views.staff_panel, name='staff_panel'),
]
