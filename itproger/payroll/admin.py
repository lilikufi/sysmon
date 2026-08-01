from django.contrib import admin
from .models import PaymentCode, PayrollPeriod, PayrollEntry, UploadedFile
@admin.register(PaymentCode)
class PaymentCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'description', 'category', 'updated_at']
    list_filter = ['category']
    search_fields = ['code', 'description']
    list_editable = ['category']
@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'year', 'month', 'half', 'created_at']
    list_filter = ['year', 'month', 'half']
    ordering = ['-year', '-month', '-half']
@admin.register(PayrollEntry)
class PayrollEntryAdmin(admin.ModelAdmin):
    list_display = ['period', 'raw_code', 'payment_code', 'amount', 'created_at']
    list_filter = ['period', 'payment_code']
    search_fields = ['raw_code', 'payment_code__description']
    raw_id_fields = ['payment_code']
@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ['file', 'file_type', 'period', 'processed', 'created_at']
    list_filter = ['file_type', 'processed']