"""
Представления (Views) для приложения анализа платежных ведомостей
"""

import json
import csv
from decimal import Decimal
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.generic import ListView, DetailView, DeleteView
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.files.storage import default_storage

from .models import PaySlip, PaySlipItem, PaymentCode, CodeDictionary
from .forms import (
    CodeDictionaryUploadForm, 
    ReceiptUploadForm, 
    PaySlipForm,
    PaySlipItemForm,
    PaymentCodeForm,
    ComparePeriodsForm
)
from .services import PaySlipService, CodeDictionaryParser


class DashboardView(View):
    """Главная страница с дашбордом"""
    
    template_name = 'analyzer/dashboard.html'
    
    def get(self, request):
        service = PaySlipService()
        
        # Получаем последнюю ведомость
        latest_payslip = PaySlip.objects.first()
        
        # Статистика
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
            'codes_count': PaymentCode.objects.count()
        }
        
        return render(request, self.template_name, context)


class UploadView(View):
    """Страница загрузки файлов"""
    
    template_name = 'analyzer/upload.html'
    
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
        
        return redirect('upload')
    
    def _handle_code_upload(self, request):
        """Обработка загрузки справочника кодов"""
        form = CodeDictionaryUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            file = request.FILES['file']
            
            # Сохраняем файл
            path = default_storage.save(f'dictionaries/{file.name}', file)
            full_path = default_storage.path(path)
            
            # Парсим и сохраняем коды
            parser = CodeDictionaryParser()
            codes = parser.parse_file(full_path)
            count = parser.save_codes(codes)
            
            # Сохраняем запись о загрузке
            CodeDictionary.objects.create(
                file=path,
                processed=True,
                codes_count=len(codes)
            )
            
            messages.success(request, f'Загружено {count} новых кодов из {len(codes)} найденных')
        else:
            messages.error(request, 'Ошибка загрузки файла')
        
        return redirect('upload')
    
    def _handle_receipt_upload(self, request):
        """Обработка загрузки квитанции"""
        form = ReceiptUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            file = request.FILES['file']
            period_str = request.POST.get('period')
            half = int(request.POST.get('half', 1))
            
            # Парсим период
            year, month = map(int, period_str.split('-'))
            period = date(year, month, 1)
            
            # Сохраняем файл
            path = default_storage.save(f'receipts/{file.name}', file)
            full_path = default_storage.path(path)
            
            # OCR обработка
            service = PaySlipService()
            income_items, deduction_items = service.process_receipt_image(full_path)
            
            if income_items or deduction_items:
                # Создаем ведомость
                payslip = service.create_payslip(
                    period=period,
                    half=half,
                    income_items=income_items,
                    deduction_items=deduction_items,
                    image=path
                )
                messages.success(request, f'Квитанция обработана. Распознано {len(income_items)} начислений и {len(deduction_items)} удержаний')
                return redirect('payslip_detail', pk=payslip.pk)
            else:
                messages.warning(request, 'Не удалось распознать данные. Попробуйте ввести вручную.')
                return redirect('manual_entry')
        
        messages.error(request, 'Ошибка загрузки файла')
        return redirect('upload')


class ManualEntryView(View):
    """Ручной ввод данных квитанции"""
    
    template_name = 'analyzer/manual_entry.html'
    
    def get(self, request):
        context = {
            'codes': PaymentCode.objects.all()
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
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
                item['rv'] = Decimal(str(item['rv'])) if item.get('rv') else None
            
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
            
            return JsonResponse({
                'success': True,
                'redirect': f'/payslip/{payslip.pk}/'
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


class PaySlipListView(ListView):
    """Список всех ведомостей"""
    
    model = PaySlip
    template_name = 'analyzer/payslip_list.html'
    context_object_name = 'payslips'
    paginate_by = 12


class PaySlipDetailView(DetailView):
    """Детальный просмотр ведомости"""
    
    model = PaySlip
    template_name = 'analyzer/payslip_detail.html'
    context_object_name = 'payslip'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payslip = self.object
        
        context['income_items'] = payslip.items.filter(item_type='income')
        context['deduction_items'] = payslip.items.filter(item_type='deduction')
        
        # Данные для круговой диаграммы
        service = PaySlipService()
        context['pie_data'] = json.dumps(service.get_category_breakdown(payslip))
        
        return context


class PaySlipDeleteView(DeleteView):
    """Удаление ведомости"""
    
    model = PaySlip
    success_url = reverse_lazy('payslip_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Ведомость удалена')
        return super().delete(request, *args, **kwargs)


class CompareView(View):
    """Сравнение периодов"""
    
    template_name = 'analyzer/compare.html'
    
    def get(self, request):
        context = {
            'form': ComparePeriodsForm(),
            'payslips': PaySlip.objects.all()
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        period1_id = request.POST.get('period1')
        period2_id = request.POST.get('period2')
        
        if period1_id and period2_id:
            payslip1 = get_object_or_404(PaySlip, pk=period1_id)
            payslip2 = get_object_or_404(PaySlip, pk=period2_id)
            
            service = PaySlipService()
            comparison = service.compare_periods(payslip1, payslip2)
            
            context = {
                'form': ComparePeriodsForm(),
                'payslips': PaySlip.objects.all(),
                'comparison': comparison,
                'comparison_json': json.dumps(comparison)
            }
            return render(request, self.template_name, context)
        
        return redirect('compare')


class CodesListView(ListView):
    """Справочник кодов"""
    
    model = PaymentCode
    template_name = 'analyzer/codes_list.html'
    context_object_name = 'codes'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = PaymentCodeForm()
        return context


class CodeCreateView(View):
    """Добавление кода"""
    
    def post(self, request):
        form = PaymentCodeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Код добавлен')
        else:
            messages.error(request, 'Ошибка добавления кода')
        return redirect('codes_list')


class CodeDeleteView(DeleteView):
    """Удаление кода"""
    
    model = PaymentCode
    success_url = reverse_lazy('codes_list')


class ExportCSVView(View):
    """Экспорт данных в CSV"""
    
    def get(self, request):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="payslips_export.csv"'
        response.write('\ufeff')  # BOM для Excel
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Период', 'Половина', 'Начислено', 'Удержано', 'К выплате'])
        
        for payslip in PaySlip.objects.all():
            half_str = '1-я половина' if payslip.half == 1 else '2-я половина'
            writer.writerow([
                payslip.period.strftime('%Y-%m'),
                half_str,
                str(payslip.total_income).replace('.', ','),
                str(payslip.total_deduction).replace('.', ','),
                str(payslip.net_pay).replace('.', ',')
            ])
        
        return response


# API Views для AJAX запросов

class APIPaySlipsView(View):
    """API: Список ведомостей"""
    
    def get(self, request):
        payslips = PaySlip.objects.all()
        data = [{
            'id': ps.pk,
            'period': ps.period.strftime('%Y-%m'),
            'half': ps.half,
            'total_income': float(ps.total_income),
            'total_deduction': float(ps.total_deduction),
            'net_pay': float(ps.net_pay)
        } for ps in payslips]
        return JsonResponse(data, safe=False)


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
        
        return JsonResponse(stats)


class APICodesView(View):
    """API: Справочник кодов"""
    
    def get(self, request):
        codes = PaymentCode.objects.all()
        data = [{
            'code': c.code,
            'description': c.description,
            'code_type': c.code_type
        } for c in codes]
        return JsonResponse(data, safe=False)
