"""
Административная панель
"""

from django.contrib import admin
from .models import PaymentCode, PaySlip, PaySlipItem, CodeDictionary


@admin.register(PaymentCode)
class PaymentCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'description', 'code_type', 'created_at']
    list_filter = ['code_type']
    search_fields = ['code', 'description']
    ordering = ['code']


class PaySlipItemInline(admin.TabularInline):
    model = PaySlipItem
    extra = 0
    fields = ['item_type', 'month', 'code', 'rv', 'amount']


@admin.register(PaySlip)
class PaySlipAdmin(admin.ModelAdmin):
    list_display = ['period', 'half', 'total_income', 'total_deduction', 'net_pay', 'created_at']
    list_filter = ['half', 'period']
    date_hierarchy = 'period'
    inlines = [PaySlipItemInline]
    readonly_fields = ['total_income', 'total_deduction', 'net_pay']


@admin.register(PaySlipItem)
class PaySlipItemAdmin(admin.ModelAdmin):
    list_display = ['payslip', 'item_type', 'month', 'code', 'rv', 'amount']
    list_filter = ['item_type', 'month']
    search_fields = ['code']


@admin.register(CodeDictionary)
class CodeDictionaryAdmin(admin.ModelAdmin):
    list_display = ['file', 'uploaded_at', 'processed', 'codes_count']
    list_filter = ['processed']
