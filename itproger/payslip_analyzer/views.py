
import json
import csv
from decimal import Decimal
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.core.files.storage import default_storage
from django.db.models import Sum, Count
from .models import PaySlip, PaySlipItem, PaymentCode, CodeDictionary
from .forms import (
    CodeDictionaryUploadForm,
    ReceiptUploadForm,
    PaySlipForm,
    PaySlipItemForm,
    PaymentCodeForm,
    ComparePeriodsForm,
    BulkItemsForm
)
from .services import PaySlipService, CodeDictionaryParser
class DashboardView(View):
    """Главная страница - дашборд"""

    template_name = 'payslip_analyzer/dashboard.html'

    def get(self, request):
        service = PaySlipService()

        # Последняя ведомость
        latest_payslip = PaySlip.objects.first()

        # Статистика за 6 месяцев
        stats = service.get_statistics(months=6)

        # Данные для графиков
        chart_data = {
            'periods': stats['periods'],
            'income': stats['income'],
            'deductions': stats['deductions'],
            'net_pay': stats['net_pay']
        }

        # Круговая диаграмма
        pie_data = {'labels': [], 'values': []}
        if latest_payslip:
            pie_data = service.get_category_breakdown(latest_payslip)

        context = {
            'latest_payslip': latest_payslip,
            'stats': stats,
            'chart_data': json.dumps(chart_data),
            'pie_data': json.dumps(pie_data),
            'payslips_count': PaySlip.objects.count(),
            'codes_count': PaymentCode.objects.filter(is_active=True).count()
        }

        return render(request, self.template_name, context)
class UploadView(View):
    """Страница загрузки файлов"""

    template_name = 'payslip_analyzer/upload.html'

    def get(self, request):
        context = {
            'code_form': CodeDictionaryUploadForm(),
            'receipt_form': ReceiptUploadForm()
        }
        return render(request, self.template_name, context)

    def post(self, request):
        action = request.POST.get('action')

        if action == 'upload_codes':
            return self._handle_code_upload(request)
        elif action == 'upload_receipt':
            return self._handle_receipt_upload(request)

        messages.error(request, 'Неизвестное действие')
        return redirect('payslip_analyzer:upload')

    def _handle_code_upload(self, request):
        """Обработка загрузки справочника кодов"""
        form = CodeDictionaryUploadForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES['file']
            original_name = file.name

            # Сохраняем файл
            path = default_storage.save(f'payslip_analyzer/dictionaries/{file.name}', file)
            full_path = default_storage.path(path)

            # Парсим и сохраняем коды
            parser = CodeDictionaryParser()
            codes, error = parser.parse_file(full_path)

            if error:
                messages.error(request, f'Ошибка парсинга: {error}')
                # Сохраняем запись с ��шибкой
                CodeDictionary.objects.create(
                    file=path,
                    original_filename=original_name,
                    processed=False,
                    error_message=error
                )
            else:
                found, added = parser.save_codes(codes)

                # Сохраняем запись об успешной загрузке
                CodeDictionary.objects.create(
                    file=path,
                    original_filename=original_name,
                    processed=True,
                    codes_found=found,
                    codes_added=added
                )

                messages.success(
                    request,
                    f'Обработано: найдено {found} кодов, добавлено {added} новых'
                )
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')

        return redirect('payslip_analyzer:upload')

    def _handle_receipt_upload(self, request):
        """Обработка загрузки квитанции"""
        form = ReceiptUploadForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES['file']
            period_str = request.POST.get('period')
            half = int(request.POST.get('half', 1))

            # Парсим период
            try:
                year, month = map(int, period_str.split('-'))
                period = date(year, month, 1)
            except (ValueError, AttributeError):
                messages.error(request, 'Неверный формат периода')
                return redirect('payslip_analyzer:upload')

            # Сохраняем файл
            path = default_storage.save(f'payslip_analyzer/receipts/{file.name}', file)
            full_path = default_storage.path(path)

            # OCR обработка
            service = PaySlipService()
            income_items, deduction_items, error = service.process_receipt_image(full_path)

            if error:
                messages.warning(request, f'OCR: {error}. Используйте ручной ввод.')
                return redirect('payslip_analyzer:manual_entry')

            if income_items or deduction_items:
                # Создаем ведомость
                payslip = service.create_payslip(
                    period=period,
                    half=half,
                    income_items=income_items,
                    deduction_items=deduction_items,
                    image=path
                )
                messages.success(
                    request,
                    f'Распознано: {len(income_items)} начислений, {len(deduction_items)} удержаний'
                )
                return redirect('payslip_analyzer:payslip_detail', pk=payslip.pk)
            else:
                messages.warning(request, 'Не удалось распознать данные. Используйте ручной ввод.')
                return redirect('payslip_analyzer:manual_entry')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')

        return redirect('payslip_analyzer:upload')
class ManualEntryView(View):
    """Ручной ввод данных квитанции"""

    template_name = 'payslip_analyzer/manual_entry.html'

    def get(self, request):
        context = {
            'codes': PaymentCode.objects.filter(is_active=True).order_by('code_type', 'code')
        }
        return render(request, self.template_name, context)

    def post(self, request):
        try:
            # Проверяем тип контента
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                # Форма
                data = {
                    'period': request.POST.get('period'),
                    'half': int(request.POST.get('half', 1)),
                    'income_items': json.loads(request.POST.get('income_items', '[]')),
                    'deduction_items': json.loads(request.POST.get('deduction_items', '[]'))
                }

            period_str = data.get('period')
            half = int(data.get('half', 1))
            income_items = data.get('income_items', [])
            deduction_items = data.get('deduction_items', [])

            # Парсим период
            year, month = map(int, period_str.split('-'))
            period = date(year, month, 1)

            # Преобразуем суммы в Decimal
            for item in income_items:
                item['amount'] = Decimal(str(item['amount']))
                if item.get('rv'):
                    item['rv'] = Decimal(str(item['rv']))

            for item in deduction_items:
                item['amount'] = Decimal(str(item['amount']))

            # Создаем ведомость
            service = PaySlipService()
            payslip = service.create_payslip(
                period=period,
                half=half,
                income_items=income_items,
                deduction_items=deduction_items
            )

            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'redirect': reverse('payslip_analyzer:payslip_detail', kwargs={'pk': payslip.pk}),
                    'payslip_id': payslip.pk
                })
            else:
                messages.success(request, 'Ведомость сохранена')
                return redirect('payslip_analyzer:payslip_detail', pk=payslip.pk)

        except Exception as e:
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=400)
            else:
                messages.error(request, f'Ошибка: {str(e)}')
                return redirect('payslip_analyzer:manual_entry')
class PaySlipListView(ListView):
    """Список всех ведомостей"""

    model = PaySlip
    template_name = 'payslip_analyzer/payslip_list.html'
    context_object_name = 'payslips'
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset()

        # Фильтр по году
        year = self.request.GET.get('year')
        if year:
            queryset = queryset.filter(period__year=year)

        return queryset.order_by('-period', '-half')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем список годов для фильтра
        years = PaySlip.objects.dates('period', 'year', order='DESC')
        context['years'] = [d.year for d in years]
        context['selected_year'] = self.request.GET.get('year')

        return context
class PaySlipDetailView(DetailView):
    """Детальный просмотр ведомости"""

    model = PaySlip
    template_name = 'payslip_analyzer/payslip_detail.html'
    context_object_name = 'payslip_analyzer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payslip = self.object

        context['income_items'] = payslip.get_income_items()
        context['deduction_items'] = payslip.get_deduction_items()

        # Данные для круговой диагра��мы
        service = PaySlipService()
        context['pie_data'] = json.dumps(service.get_category_breakdown(payslip))

        # Предыдущая и следующая ведомости
        context['prev_payslip'] = PaySlip.objects.filter(
            period__lt=payslip.period
        ).first() or PaySlip.objects.filter(
            period=payslip.period, half__lt=payslip.half
        ).first()

        context['next_payslip'] = PaySlip.objects.filter(
            period__gt=payslip.period
        ).last() or PaySlip.objects.filter(
            period=payslip.period, half__gt=payslip.half
        ).last()

        return context
class PaySlipDeleteView(DeleteView):
    """Удаление ведомости"""

    model = PaySlip
    template_name = 'payslip_analyzer/payslip_confirm_delete.html'
    success_url = reverse_lazy('payslip_analyzer:payslip_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Ведомость удалена')
        return super().delete(request, *args, **kwargs)
class CompareView(View):
    """Сравнение периодов"""

    template_name = 'payslip_analyzer/compare.html'

    def get(self, request):
        context = {
            'form': ComparePeriodsForm(),
            'payslips': PaySlip.objects.all()
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = ComparePeriodsForm(request.POST)

        if form.is_valid():
            period1 = form.cleaned_data['period1']
            period2 = form.cleaned_data['period2']

            service = PaySlipService()
            comparison = service.compare_periods(period1, period2)

            context = {
                'form': form,
                'payslips': PaySlip.objects.all(),
                'comparison': comparison,
                'comparison_json': json.dumps(comparison)
            }
            return render(request, self.template_name, context)

        context = {
            'form': form,
            'payslips': PaySlip.objects.all()
        }
        return render(request, self.template_name, context)
class CodesListView(ListView):
    """Справочник кодов"""

    model = PaymentCode
    template_name = 'payslip_analyzer/codes_list.html'
    context_object_name = 'codes'

    def get_queryset(self):
        return PaymentCode.objects.order_by('code_type', 'code')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = PaymentCodeForm()
        context['income_codes'] = self.get_queryset().filter(code_type='income')
        context['deduction_codes'] = self.get_queryset().filter(code_type='deduction')
        return context
class CodeCreateView(CreateView):
    """Добавление кода"""

    model = PaymentCode
    form_class = PaymentCodeForm
    success_url = reverse_lazy('payslip_analyzer:codes_list')

    def form_valid(self, form):
        messages.success(self.request, 'Код добавлен')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Ошибка добавления кода')
        return redirect('payslip_analyzer:codes_list')
class CodeDeleteView(DeleteView):
    """Удаление кода"""

    model = PaymentCode
    success_url = reverse_lazy('payslip_analyzer:codes_list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Код удалён')
        return super().delete(request, *args, **kwargs)
class LoadDefaultCodesView(View):
    """Загрузка стандартных кодов"""

    def post(self, request):
        service = PaySlipService()
        count = service.load_default_codes()
        messages.success(request, f'Добавлено {count} стандартных кодов')
        return redirect('payslip_analyzer:codes_list')
class ExportCSVView(View):
    """Экспорт данных в CSV"""

    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="payslips_export.csv"'
        response.write('\ufeff')  # BOM для Excel

        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Период', 'Половина', 'Начислено', 'Удержано', 'К выплате', 'Дата создания'])

        for payslip in PaySlip.objects.all():
            half_str = '1-я половина' if payslip.half == 1 else '2-я половина'
            writer.writerow([
                payslip.period.strftime('%Y-%m'),
                half_str,
                str(payslip.total_income).replace('.', ','),
                str(payslip.total_deduction).replace('.', ','),
                str(payslip.net_pay).replace('.', ','),
                payslip.created_at.strftime('%d.%m.%Y %H:%M')
            ])

        return response
class ExportDetailCSVView(View):
    """Экспорт детальных данных ведомости в CSV"""

    def get(self, request, pk):
        payslip = get_object_or_404(PaySlip, pk=pk)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f"payslip_{payslip.period.strftime('%Y_%m')}_{payslip.half}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('\ufeff')

        writer = csv.writer(response, delimiter=';')

        # Заголовок
        writer.writerow([f'Ведомость: {payslip.get_period_display()}'])
        writer.writerow([])

        # Начисления
        writer.writerow(['НАЧИСЛЕНИЯ'])
        writer.writerow(['Месяц', 'Код', 'Описание', 'РВ', 'Сумма'])
        for item in payslip.get_income_items():
            writer.writerow([
                item.month,
                item.code,
                item.description,
                str(item.rv or '').replace('.', ','),
                str(item.amount).replace('.', ',')
            ])
        writer.writerow(['', '', '', 'Итого:', str(payslip.total_income).replace('.', ',')])
        writer.writerow([])

        # Удержания
        writer.writerow(['УДЕРЖАНИЯ'])
        writer.writerow(['Месяц', 'Код', 'Описание', 'Сумма'])
        for item in payslip.get_deduction_items():
            writer.writerow([
                item.month,
                item.code,
                item.description,
                str(item.amount).replace('.', ',')
            ])
        writer.writerow(['', '', 'Итого:', str(payslip.total_deduction).replace('.', ',')])
        writer.writerow([])

        # Итог
        writer.writerow(['К ВЫПЛАТЕ:', str(payslip.net_pay).replace('.', ',')])

        return response
# ==================== API Views ====================
class APIPaySlipsView(View):
    """API: Список ведомостей"""

    def get(self, request):
        payslips = PaySlip.objects.all()[:50]
        data = [{
            'id': ps.pk,
            'period': ps.period.strftime('%Y-%m'),
            'half': ps.half,
            'half_display': ps.get_half_display(),
            'period_display': ps.get_period_display(),
            'total_income': float(ps.total_income),
            'total_deduction': float(ps.total_deduction),
            'net_pay': float(ps.net_pay),
            'created_at': ps.created_at.isoformat()
        } for ps in payslips]
        return JsonResponse(data, safe=False)
class APIPaySlipDetailView(View):
    """API: Детали ведомости"""

    def get(self, request, pk):
        payslip = get_object_or_404(PaySlip, pk=pk)

        income_items = [{
            'month': item.month,
            'code': item.code,
            'description': item.description,
            'rv': float(item.rv) if item.rv else None,
            'amount': float(item.amount)
        } for item in payslip.get_income_items()]

        deduction_items = [{
            'month': item.month,
            'code': item.code,
            'description': item.description,
            'amount': float(item.amount)
        } for item in payslip.get_deduction_items()]

        data = {
            'id': payslip.pk,
            'period': payslip.period.strftime('%Y-%m'),
            'half': payslip.half,
            'period_display': payslip.get_period_display(),
            'total_income': float(payslip.total_income),
            'total_deduction': float(payslip.total_deduction),
            'net_pay': float(payslip.net_pay),
            'income_items': income_items,
            'deduction_items': deduction_items
        }
        return JsonResponse(data)
class APIStatisticsView(View):
    """API: Статистика"""

    def get(self, request):
        months = int(request.GET.get('months', 6))
        service = PaySlipService()
        stats = service.get_statistics(months=months)

        # Конвертируем Decimal в float
        stats['total_income'] = float(stats['total_income'])
        stats['total_deductions'] = float(stats['total_deductions'])
        stats['total_net_pay'] = float(stats['total_net_pay'])
        stats['avg_income'] = float(stats['avg_income'])
        stats['avg_deductions'] = float(stats['avg_deductions'])
        stats['avg_net_pay'] = float(stats['avg_net_pay'])

        return JsonResponse(stats)
class APICodesView(View):
    """API: Справочник кодов"""

    def get(self, request):
        code_type = request.GET.get('type')  # income, deduction или None (все)

        queryset = PaymentCode.objects.filter(is_active=True)
        if code_type:
            queryset = queryset.filter(code_type=code_type)

        data = [{
            'id': c.pk,
            'code': c.code,
            'description': c.description,
            'code_type': c.code_type
        } for c in queryset.order_by('code')]

        return JsonResponse(data, safe=False)
class APITrendsView(View):
    """API: Тренды по коду"""

    def get(self, request, code):
        months = int(request.GET.get('months', 12))
        service = PaySlipService()
        data = service.get_trends(code, months=months)
        return JsonResponse(data)
