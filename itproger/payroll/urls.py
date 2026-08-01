from django.urls import path
from . import views

app_name = 'payroll'
urlpatterns = [
    # Главная страница
    path('', views.dashboard, name='dashboard'),

    # Загрузка файлов
    path('upload/codebook/', views.upload_codebook, name='upload_codebook'),
    path('upload/receipt/', views.upload_receipt, name='upload_receipt'),
    path('manual-entry/', views.manual_entry, name='manual_entry'),

    # Справочник кодов
    path('codebook/', views.codebook_list, name='codebook_list'),

    # Периоды
    path('periods/', views.period_list, name='period_list'),
    path('periods/<int:period_id>/', views.period_detail, name='period_detail'),
    path('periods/<int:period_id>/delete/', views.delete_period, name='delete_period'),

    # Записи
    path('entries/<int:entry_id>/delete/', views.delete_entry, name='delete_entry'),

    # Аналитика
    path('analytics/', views.analytics, name='analytics'),

    # API
    path('api/chart-data/', views.api_chart_data, name='api_chart_data'),
]