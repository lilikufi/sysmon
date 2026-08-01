from django.urls import path
from . import views
from .views import UserPasswordChangeView

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('password/', UserPasswordChangeView.as_view(), name='password_change'),

]