"""
URL маршруты для приложения analyzer
"""

from django.urls import path
from . import views

urlpatterns = [
    # Главная страница
    path('', views.DashboardView.as_view(), name='dashboard'),
    
    # Загрузка файлов
    path('upload/', views.UploadView.as_view(), name='upload'),
    path('manual-entry/', views.ManualEntryView.as_view(), name='manual_entry'),
    
    # Ведомости
    path('payslips/', views.PaySlipListView.as_view(), name='payslip_list'),
    path('payslip/<int:pk>/', views.PaySlipDetailView.as_view(), name='payslip_detail'),
    path('payslip/<int:pk>/delete/', views.PaySlipDeleteView.as_view(), name='payslip_delete'),
    
    # Сравнение
    path('compare/', views.CompareView.as_view(), name='compare'),
    
    # Справочник кодов
    path('codes/', views.CodesListView.as_view(), name='codes_list'),
    path('codes/add/', views.CodeCreateView.as_view(), name='code_create'),
    path('codes/<int:pk>/delete/', views.CodeDeleteView.as_view(), name='code_delete'),
    
    # Экспорт
    path('export/csv/', views.ExportCSVView.as_view(), name='export_csv'),
    
    # API endpoints
    path('api/payslips/', views.APIPaySlipsView.as_view(), name='api_payslips'),
    path('api/statistics/', views.APIStatisticsView.as_view(), name='api_statistics'),
    path('api/codes/', views.APICodesView.as_view(), name='api_codes'),
]
