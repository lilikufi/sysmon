"""
URL маршруты для PaySlip Analyzer
"""
from django.urls import path
from . import views

app_name = 'payslip_analyzer'
urlpatterns = [
    # Главная страница - дашборд
    path('', views.DashboardView.as_view(), name='dashboard'),

    # Загрузка файлов
    path('upload/', views.UploadView.as_view(), name='upload'),
    path('manual-entry/', views.ManualEntryView.as_view(), name='manual_entry'),

    # Ведомости
    path('payslips/', views.PaySlipListView.as_view(), name='payslip_list'),
    path('payslips/<int:pk>/', views.PaySlipDetailView.as_view(), name='payslip_detail'),
    path('payslips/<int:pk>/delete/', views.PaySlipDeleteView.as_view(), name='payslip_delete'),
    path('payslips/<int:pk>/export/', views.ExportDetailCSVView.as_view(), name='payslip_export'),

    # Сравнение периодов
    path('compare/', views.CompareView.as_view(), name='compare'),

    # Справочник кодов
    path('codes/', views.CodesListView.as_view(), name='codes_list'),
    path('codes/add/', views.CodeCreateView.as_view(), name='code_create'),
    path('codes/<int:pk>/delete/', views.CodeDeleteView.as_view(), name='code_delete'),
    path('codes/load-defaults/', views.LoadDefaultCodesView.as_view(), name='load_default_codes'),

    # Экспорт
    path('export/csv/', views.ExportCSVView.as_view(), name='export_csv'),

    # ==================== API ====================
    path('api/payslips/', views.APIPaySlipsView.as_view(), name='api_payslips'),
    path('api/payslips/<int:pk>/', views.APIPaySlipDetailView.as_view(), name='api_payslip_detail'),
    path('api/statistics/', views.APIStatisticsView.as_view(), name='api_statistics'),
    path('api/codes/', views.APICodesView.as_view(), name='api_codes'),
    path('api/trends/<str:code>/', views.APITrendsView.as_view(), name='api_trends'),
]