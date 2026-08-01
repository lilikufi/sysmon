#
# from django.contrib import admin
# from django.utils.html import format_html
# from .models import PaymentCode, PaySlip, PaySlipItem, CodeDictionary
# @admin.register(PaymentCode)
# class PaymentCodeAdmin(admin.ModelAdmin):
#     list_display = ['code', 'description', 'code_type_badge', 'is_active', 'created_at']
#     list_filter = ['code_type', 'is_active']
#     search_fields = ['code', 'description']
#     ordering = ['code']
#     list_editable = ['is_active']
#
#     def code_type_badge(self, obj):
#         if obj.code_type == 'income':
#             color = '#00ff88'
#             label = 'Начисление'
#         else:
#             color = '#ff006e'
#             label = 'Удержание'
#         return format_html(
#             '<span style="background: {}; color: #000; padding: 3px 8px; '
#             'border-radius: 4px; font-size: 11px;">{}</span>',
#             color, label
#         )
#     code_type_badge.short_description = 'Тип'
#
#     actions = ['load_default_codes']
#
#     @admin.action(description='Загрузить стандартные коды')
#     def load_default_codes(self, request, queryset):
#         codes = PaymentCode.get_default_codes()
#         created = 0
#         for code_data in codes:
#             obj, is_created = PaymentCode.objects.get_or_create(
#                 code=code_data['code'],
#                 defaults=code_data
#             )
#             if is_created:
#                 created += 1
#         self.message_user(request, f'Добавлено {created} новых кодов')
# class PaySlipItemInline(admin.TabularInline):
#     model = PaySlipItem
#     extra = 1
#     fields = ['item_type', 'month', 'code', 'code_ref', 'rv', 'amount']
#     autocomplete_fields = ['code_ref']
#
#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related('code_ref')
# @admin.register(PaySlip)
# class PaySlipAdmin(admin.ModelAdmin):
#     list_display = [
#         'period_display', 'half_badge', 'total_income_display',
#         'total_deduction_display', 'net_pay_display', 'created_at'
#     ]
#     list_filter = ['half', 'period']
#     date_hierarchy = 'period'
#     inlines = [PaySlipItemInline]
#     readonly_fields = ['total_income', 'total_deduction', 'net_pay', 'created_at', 'updated_at']
#
#     fieldsets = (
#         ('Период', {
#             'fields': ('period', 'half')
#         }),
#         ('Итоги', {
#             'fields': ('total_income', 'total_deduction', 'net_pay'),
#             'classes': ('collapse',)
#         }),
#         ('Дополнительно', {
#             'fields': ('receipt_image', 'notes', 'created_at', 'updated_at'),
#             'classes': ('collapse',)
#         }),
#     )
#
#     def period_display(self, obj):
#         return obj.period.strftime('%B %Y')
#     period_display.short_description = 'Период'
#     period_display.admin_order_field = 'period'
#
#     def half_badge(self, obj):
#         if obj.half == 1:
#             color = '#00d4ff'
#             label = '1-я пол.'
#         else:
#             color = '#b347d9'
#             label = '2-я пол.'
#         return format_html(
#             '<span style="background: {}; color: #000; padding: 3px 8px; '
#             'border-radius: 4px; font-size: 11px;">{}</span>',
#             color, label
#         )
#     half_badge.short_description = 'Половина'
#
#     def total_income_display(self, obj):
#         return format_html(
#             '<span style="color: #00ff88; font-weight: bold;">{:,.2f} ₽</span>',
#             obj.total_income
#         )
#     total_income_display.short_description = 'Начислено'
#
#     def total_deduction_display(self, obj):
#         return format_html(
#             '<span style="color: #ff006e; font-weight: bold;">{:,.2f} ₽</span>',
#             obj.total_deduction
#         )
#     total_deduction_display.short_description = 'Удержано'
#
#     def net_pay_display(self, obj):
#         return format_html(
#             '<span style="color: #00d4ff; font-weight: bold;">{:,.2f} ₽</span>',
#             obj.net_pay
#         )
#     net_pay_display.short_description = 'К выплате'
#
#     actions = ['recalculate_totals']
#
#     @admin.action(description='Пересчитать итоги')
#     def recalculate_totals(self, request, queryset):
#         for payslip_analyzer in queryset:
#             payslip_analyzer.calculate_totals()
#         self.message_user(request, f'Пересчитано {queryset.count()} ведомостей')
# @admin.register(PaySlipItem)
# class PaySlipItemAdmin(admin.ModelAdmin):
#     list_display = ['payslip_analyzer', 'item_type_badge', 'month', 'code', 'description', 'rv', 'amount_display']
#     list_filter = ['item_type', 'month', 'payslip__period']
#     search_fields = ['code', 'code_ref__description']
#     autocomplete_fields = ['code_ref', 'payslip_analyzer']
#
#     def item_type_badge(self, obj):
#         if obj.item_type == 'income':
#             color = '#00ff88'
#         else:
#             color = '#ff006e'
#         return format_html(
#             '<span style="background: {}; color: #000; padding: 3px 8px; '
#             'border-radius: 4px; font-size: 11px;">{}</span>',
#             color, obj.get_item_type_display()
#         )
#     item_type_badge.short_description = 'Тип'
#
#     def amount_display(self, obj):
#         color = '#00ff88' if obj.item_type == 'income' else '#ff006e'
#         return format_html(
#             '<span style="color: {}; font-weight: bold;">{:,.2f} ₽</span>',
#             color, obj.amount
#         )
#     amount_display.short_description = 'Сумма'
# @admin.register(CodeDictionary)
# class CodeDictionaryAdmin(admin.ModelAdmin):
#     list_display = ['original_filename', 'uploaded_at', 'processed_badge', 'codes_found', 'codes_added']
#     list_filter = ['processed']
#     readonly_fields = ['uploaded_at', 'processed', 'codes_found', 'codes_added', 'error_message']
#
#     def processed_badge(self, obj):
#         if obj.processed:
#             color = '#00ff88'
#             label = '✓ Обработан'
#         else:
#             color = '#ff9500'
#             label = '⏳ Ожидает'
#         return format_html(
#             '<span style="color: {};">{}</span>',
#             color, label
#         )
#     processed_badge.short_description = 'Статус'
