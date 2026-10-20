from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path, reverse_lazy, include
from . import views

urlpatterns = [
    path('auth/apps/<slug:slug>/session/', views.application_session, name='application-session'),
    path('auth/apps/<slug:slug>/open/', views.open_application, name='open-application'),
    path('auth/oidc/', include(('portal.oidc', 'oauth2_provider'), namespace='oauth2_provider')),
    path('api/member-session', views.session),
    path('internal/authorize', views.authorize),
    path('auth/', auth.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('auth/logout/', auth.LogoutView.as_view(), name='logout'),
    path('auth/account/', views.account, name='account'),
    path('auth/denied/', views.denied),
    path('auth/password/', auth.PasswordChangeView.as_view(template_name='registration/form.html',
         success_url=reverse_lazy('password_change_done')), name='password_change'),
    path('auth/password/done/', auth.PasswordChangeDoneView.as_view(template_name='registration/done.html'), name='password_change_done'),
    path('auth/reset/', auth.PasswordResetView.as_view(template_name='registration/reset.html',
         email_template_name='registration/reset_email.txt', subject_template_name='registration/reset_subject.txt',
         success_url=reverse_lazy('password_reset_done')), name='password_reset'),
    path('auth/reset/sent/', auth.PasswordResetDoneView.as_view(template_name='registration/reset_sent.html'), name='password_reset_done'),
    path('auth/reset/<uidb64>/<token>/', auth.PasswordResetConfirmView.as_view(template_name='registration/reset_confirm.html',
         success_url=reverse_lazy('password_reset_complete')), name='password_reset_confirm'),
    path('auth/reset/done/', auth.PasswordResetCompleteView.as_view(template_name='registration/done.html'), name='password_reset_complete'),
    path('auth/admin/', admin.site.urls),
]
