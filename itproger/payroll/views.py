import json
import os
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Sum
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
from .models import PaymentCode, PayrollPeriod, PayrollEntry, UploadedFile
from .forms import CodebookUploadForm, ReceiptUploadForm, ManualEntryForm, PeriodFilterForm
from .services import CodebookParser, ReceiptParser, ReceiptOCR, PayrollAnalytics
def dashboard(request):
    """Главная страница - дашборд"""
    periods = PayrollPeriod.objects.all()[:12]
    latest_period = periods.first() if periods else None

    # Данные для графиков
    pie_data = {}
    trend_data = {}
    total_amount = Decimal('0')
    entries_count = 0

    if latest_period:
        entries = PayrollEntry.objects.filter(period=latest_period)
        pie_data = PayrollAnalytics.get_pie_chart_data(entries)
        total_amount = entries.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        entries_count = entries.count()

    # Тренд за последние периоды
    if periods:
        periods_with_entries = [
            (p, PayrollEntry.objects.filter(period=p))
            for p in reversed(list(periods[:6]))
        ]
        trend_data = PayrollAnalytics.get_trend_data(periods_with_entries)

    context = {
        'periods': periods,
        'latest_period': latest_period,
        'pie_data': json.dumps(pie_data),
        'trend_data': json.dumps(trend_data),
        'total_amount': total_amount,
        'entries_count': entries_count,
        'codes_count': PaymentCode.objects.count(),
    }

    return render(request, 'payroll/dashboard.html', context)
def upload_codebook(request):
    """Загрузка справочника кодов"""
    if request.method == 'POST':
        form = CodebookUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']

            # Сохраняем файл
            file_obj = UploadedFile.objects.create(
                file=uploaded_file,
                file_type='codebook'
            )

            file_path = file_obj.file.path
            ext = uploaded_file.name.split('.')[-1].lower()

            try:
                if ext == 'txt':
                    codes = CodebookParser.parse_txt_file(file_path)
                elif ext == 'pdf':
                    codes = CodebookParser.parse_pdf_file(file_path)
                else:
                    codes = []
                    messages.warning(request, f'Неподдерживаемый формат: {ext}')

                if not codes:
                    # Читаем файл для отладки
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()[:500]
                    except:
                        try:
                            with open(file_path, 'r', encoding='cp1251') as f:
                                content = f.read()[:500]
                        except:
                            content = "(не удалось прочитать)"

                    messages.warning(
                        request,
                        f'Не удалось распознать коды в файле. Содержимое: {content[:200]}...'
                    )
                else:
                    # Сохраняем коды в базу
                    created_count = 0
                    updated_count = 0
                    for code_data in codes:
                        obj, created = PaymentCode.objects.update_or_create(
                            code=code_data['code'],
                            defaults={'description': code_data['description']}
                        )
                        if created:
                            created_count += 1
                        else:
                            updated_count += 1

                    file_obj.processed = True
                    file_obj.save()

                    messages.success(
                        request,
                        f'Справочник загружен! Создано: {created_count}, обновлено: {updated_count}'
                    )

            except ImportError as e:
                messages.error(request, str(e))
            except Exception as e:
                import traceback
                messages.error(request, f'Ошибка обработки файла: {str(e)}')

            return redirect('payroll:codebook_list')
    else:
        form = CodebookUploadForm()

    return render(request, 'payroll/upload_codebook.html', {'form': form})
def upload_receipt(request):
    """Загрузка квитанции"""
    if request.method == 'POST':
        form = ReceiptUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            year = int(form.cleaned_data['year'])
            month = int(form.cleaned_data['month'])
            half = int(form.cleaned_data['half'])

            # Создаем или получаем период
            period, _ = PayrollPeriod.objects.get_or_create(
                year=year, month=month, half=half
            )

            # Сохраняем файл
            file_obj = UploadedFile.objects.create(
                file=uploaded_file,
                file_type='receipt',
                period=period
            )

            file_path = file_obj.file.path
            ext = uploaded_file.name.split('.')[-1].lower()

            try:
                entries = []

                # Обработка в зависимости от типа файла
                if ext == 'txt':
                    # TXT файл - используем ReceiptParser
                    entries = ReceiptParser.parse_txt_file(file_path)

                elif ext in ['jpg', 'jpeg', 'png']:
                    # Изображение - используем OCR
                    text = ReceiptOCR.extract_text_from_image(file_path)
                    entries = ReceiptParser.parse_receipt_text(text)

                elif ext == 'pdf':
                    # PDF - пробуем извлечь текст или OCR
                    text = ReceiptOCR.extract_text_from_pdf(file_path)
                    entries = ReceiptParser.parse_receipt_text(text)

                if not entries:
                    # Читаем содержимое для отладки
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()[:1000]
                    except:
                        try:
                            with open(file_path, 'r', encoding='cp1251') as f:
                                content = f.read()[:1000]
                        except:
                            content = "(бинарный файл)"

                    messages.warning(
                        request,
                        f'Не удалось распознать данные. Используйте ручной ввод. Содержимое: {content[:300]}...'
                    )
                    return redirect('payroll:manual_entry')

                # Сохраняем записи
                created_count = 0
                for entry_data in entries:
                    code = entry_data['code']
                    payment_code = PaymentCode.objects.filter(code=code).first()

                    PayrollEntry.objects.create(
                        period=period,
                        payment_code=payment_code,
                        raw_code=code,
                        amount=entry_data['amount']
                    )
                    created_count += 1

                file_obj.processed = True
                file_obj.save()

                messages.success(
                    request,
                    f'Квитанция обработана! Распознано записей: {created_count}'
                )

                return redirect('payroll:period_detail', period_id=period.id)

            except ImportError as e:
                messages.warning(request, f'{str(e)}. Используйте ручной ввод.')
                return redirect('payroll:manual_entry')
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                messages.error(request, f'Ошибка обработки: {str(e)}. Используйте ручной ввод.')
                return redirect('payroll:manual_entry')
    else:
        form = ReceiptUploadForm()

    return render(request, 'payroll/upload_receipt.html', {'form': form})
def manual_entry(request):
    """Ручной ввод данных"""
    if request.method == 'POST':
        form = ManualEntryForm(request.POST)
        if form.is_valid():
            year = int(form.cleaned_data['year'])
            month = int(form.cleaned_data['month'])
            half = int(form.cleaned_data['half'])
            entries_data = form.cleaned_data['entries_data']

            # Создаем период
            period, _ = PayrollPeriod.objects.get_or_create(
                year=year, month=month, half=half
            )

            # Парсим и сохраняем записи
            created_count = 0
            lines = entries_data.strip().split('\n')

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Пробуем разные разделители
                parts = None
                for sep in [' - ', '-', ':', '\t', '  ']:
                    if sep in line:
                        parts = line.split(sep, 1)
                        break

                if parts and len(parts) == 2:
                    code = parts[0].strip()
                    try:
                        amount = Decimal(parts[1].strip().replace(',', '.').replace(' ', ''))
                        payment_code = PaymentCode.objects.filter(code=code).first()

                        PayrollEntry.objects.create(
                            period=period,
                            payment_code=payment_code,
                            raw_code=code,
                            amount=amount
                        )
                        created_count += 1
                    except:
                        continue

            messages.success(request, f'Добавлено записей: {created_count}')
            return redirect('payroll:period_detail', period_id=period.id)
    else:
        form = ManualEntryForm()

    return render(request, 'payroll/manual_entry.html', {'form': form})
def codebook_list(request):
    """Список кодов оплат"""
    codes = PaymentCode.objects.all()
    return render(request, 'payroll/codebook_list.html', {'codes': codes})
def period_list(request):
    """Список периодов"""
    periods = PayrollPeriod.objects.annotate(
        total_amount=Sum('entries__amount'),
        entries_count=Sum('entries__id')
    )
    return render(request, 'payroll/period_list.html', {'periods': periods})
def period_detail(request, period_id):
    """Детали периода"""
    period = get_object_or_404(PayrollPeriod, id=period_id)
    entries = PayrollEntry.objects.filter(period=period).select_related('payment_code')

    summary = PayrollAnalytics.get_period_summary(entries)
    pie_data = PayrollAnalytics.get_pie_chart_data(entries)

    # Сравнение с предыдущим периодом
    comparison = None
    prev_periods = PayrollPeriod.objects.filter(
        year__lte=period.year,
        month__lt=period.month if period.year == period.year else 12
    ).exclude(id=period.id).order_by('-year', '-month', '-half')[:1]

    if prev_periods:
        prev_period = prev_periods[0]
        prev_entries = PayrollEntry.objects.filter(period=prev_period)
        comparison = PayrollAnalytics.get_comparison_data(entries, prev_entries)
        comparison['prev_period'] = prev_period

    context = {
        'period': period,
        'entries': entries,
        'summary': summary,
        'pie_data': json.dumps(pie_data),
        'comparison': comparison,
    }

    return render(request, 'payroll/period_detail.html', context)
def analytics(request):
    """Страница аналитики"""
    periods = PayrollPeriod.objects.all()

    # Получаем данные для сравнения
    period1_id = request.GET.get('period1')
    period2_id = request.GET.get('period2')

    comparison = None
    period1 = None
    period2 = None

    if period1_id and period2_id:
        period1 = PayrollPeriod.objects.filter(id=period1_id).first()
        period2 = PayrollPeriod.objects.filter(id=period2_id).first()

        if period1 and period2:
            entries1 = PayrollEntry.objects.filter(period=period1)
            entries2 = PayrollEntry.objects.filter(period=period2)
            comparison = PayrollAnalytics.get_comparison_data(entries1, entries2)

    # Тренды
    periods_with_entries = [
        (p, PayrollEntry.objects.filter(period=p))
        for p in reversed(list(periods[:12]))
    ]
    trend_data = PayrollAnalytics.get_trend_data(periods_with_entries)

    context = {
        'periods': periods,
        'comparison': comparison,
        'period1': period1,
        'period2': period2,
        'trend_data': json.dumps(trend_data),
    }

    return render(request, 'payroll/analytics.html', context)
@require_POST
def delete_entry(request, entry_id):
    """Удаление записи"""
    entry = get_object_or_404(PayrollEntry, id=entry_id)
    period_id = entry.period.id
    entry.delete()
    messages.success(request, 'Запись удалена')
    return redirect('payroll:period_detail', period_id=period_id)
@require_POST
def delete_period(request, period_id):
    """Удаление периода"""
    period = get_object_or_404(PayrollPeriod, id=period_id)
    period.delete()
    messages.success(request, 'Период удален')
    return redirect('payroll:period_list')
def api_chart_data(request):
    """API для получения данных графиков"""
    period_id = request.GET.get('period_id')
    chart_type = request.GET.get('type', 'pie')

    if period_id:
        entries = PayrollEntry.objects.filter(period_id=period_id)
    else:
        entries = PayrollEntry.objects.all()

    if chart_type == 'pie':
        data = PayrollAnalytics.get_pie_chart_data(entries)
    else:
        periods = PayrollPeriod.objects.all()[:12]
        periods_with_entries = [
            (p, PayrollEntry.objects.filter(period=p))
            for p in reversed(list(periods))
        ]
        data = PayrollAnalytics.get_trend_data(periods_with_entries)

    return JsonResponse(data)
