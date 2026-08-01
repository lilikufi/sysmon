import re
import os
import logging
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple, Optional
# Настройка логирования
logger = logging.getLogger(__name__)
# Опциональные импорты для OCR и PDF
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
try:
    import pdf2image
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
class CodebookParser:
    """Парсер справочника кодов оплат"""

    @staticmethod
    def parse_text(content: str) -> List[Dict[str, str]]:
        """Парсинг текстового содержимого справочника"""
        codes = []
        lines = content.strip().split('\n')

        print(f"[DEBUG] Парсинг справочника: {len(lines)} строк")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Пропускаем строки-разделители таблицы (|---|---|)
            if re.match(r'^[\|\s\-:]+$', line):
                continue

            # Проверяем формат таблицы с разделителями |
            if '|' in line:
                parts = [p.strip() for p in line.split('|')]
                parts = [p for p in parts if p]  # Убираем пустые

                if len(parts) >= 2:
                    # Пропускаем заголовок таблицы
                    first_part_lower = parts[0].lower()
                    if any(skip in first_part_lower for skip in ['код', 'code', 'наименование', 'вид', 'мес']):
                        continue

                    # Ищем код (число) и описание
                    code = None
                    description = None

                    for i, part in enumerate(parts):
                        # Если часть - это число (код)
                        if re.match(r'^\d+$', part) and not code:
                            code = part
                            # Описание - следующая часть
                            if i + 1 < len(parts):
                                description = parts[i + 1]
                            break

                    if code and description:
                        codes.append({
                            'code': code,
                            'description': description
                        })
                        print(f"[DEBUG] Найден код: {code} -> {description[:50]}...")
                        continue

            # Пропускаем строки-заголовки (для обычного формата)
            lower_line = line.lower()
            if any(skip in lower_line for skip in ['код', 'описание', 'наименование', '---', '===', 'code', 'description']):
                if not any(c.isdigit() for c in line[:10]):
                    continue

            code = None
            description = None

            # Метод 1: разделители
            for sep in [' - ', ' – ', ' — ', ':', '\t', '  ']:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2:
                        potential_code = parts[0].strip()
                        potential_desc = parts[1].strip()
                        if potential_code and potential_desc and len(potential_code) <= 20:
                            code = potential_code
                            description = potential_desc
                            break

            # Метод 2: regex паттерны
            if not code:
                patterns = [
                    r'^([A-Za-zА-Яа-яЁё0-9_\.]+)\s*[-–—:]\s*(.+)$',
                    r'^(\d+)\s+([A-Za-zА-Яа-яЁё].+)$',
                ]
                for pattern in patterns:
                    match = re.match(pattern, line)
                    if match:
                        potential_code = match.group(1).strip()
                        potential_desc = match.group(2).strip()
                        if potential_code and potential_desc and len(potential_code) <= 20:
                            code = potential_code
                            description = potential_desc
                            break

            if code and description:
                description = re.sub(r'^[-–—:\s]+', '', description).strip()
                if description:
                    codes.append({
                        'code': code,
                        'description': description
                    })
                    print(f"[DEBUG] Найден код: {code} -> {description[:50]}...")

        print(f"[DEBUG] Всего найдено кодов: {len(codes)}")
        return codes

    @staticmethod
    def parse_txt_file(file_path: str) -> List[Dict[str, str]]:
        """Парсинг TXT файла"""
        encodings = ['utf-8', 'cp1251', 'cp866', 'latin-1', 'koi8-r', 'utf-16']
        content = None

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                print(f"[DEBUG] Файл прочитан с кодировкой: {encoding}")
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            print("[ERROR] Не удалось прочитать файл ни в одной кодировке")
            return []

        return CodebookParser.parse_text(content)

    @staticmethod
    def parse_pdf_file(file_path: str) -> List[Dict[str, str]]:
        """Парсинг PDF файла"""
        if not PYPDF2_AVAILABLE:
            raise ImportError("PyPDF2 не установлен. Установите: pip install PyPDF2")

        text = ""
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        print(f"[DEBUG] Извлечено из PDF: {len(text)} символов")
        return CodebookParser.parse_text(text)
class ReceiptParser:
    """Парсер квитанций (расчетных листков)"""

    @staticmethod
    def parse_receipt_text(content: str) -> List[Dict]:
        """
        Парсинг текста квитанции в формате КБМ
        Формат строки: | 10  4      | 20        | 29017.39       | 10 700    | 16462.38  |
        где: месяц код | рв | сумма начисления | месяц код | сумма удержания
        """
        entries = []
        lines = content.strip().split('\n')

        print(f"[DEBUG] Парсинг квитанции: {len(lines)} строк")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Пропускаем разделители и заголовки
            if re.match(r'^[\|\s\-:]+$', line):
                continue

            lower_line = line.lower()
            if any(skip in lower_line for skip in ['мес.код', 'код рв', 'сумма', 'нач.', 'удерж']):
                continue

            # Обрабатываем строки таблицы с |
            if '|' in line:
                # Разбиваем по |
                parts = [p.strip() for p in line.split('|')]
                parts = [p for p in parts if p]  # Убираем пустые

                print(f"[DEBUG] Строка квитанции: {parts}")

                if len(parts) >= 2:
                    # Парсим начисления (первая часть)
                    accrual_entry = ReceiptParser._parse_accrual_cell(parts[0], parts[1] if len(parts) > 1 else '', parts[2] if len(parts) > 2 else '')
                    if accrual_entry:
                        entries.append(accrual_entry)
                        print(f"[DEBUG] Начисление: код {accrual_entry['code']} = {accrual_entry['amount']}")

                    # Парсим удержания (вторая часть, если есть)
                    if len(parts) >= 4:
                        deduction_entry = ReceiptParser._parse_deduction_cell(parts[3], parts[4] if len(parts) > 4 else '')
                        if deduction_entry:
                            deduction_entry['is_deduction'] = True
                            entries.append(deduction_entry)
                            print(f"[DEBUG] Удержание: код {deduction_entry['code']} = {deduction_entry['amount']}")

        # Если таблица не распознана, пробуем простой формат
        if not entries:
            entries = ReceiptParser._parse_simple_format(content)

        print(f"[DEBUG] Всего найдено записей: {len(entries)}")
        return entries

    @staticmethod
    def _parse_accrual_cell(cell1: str, cell2: str, cell3: str) -> Optional[Dict]:
        """
        Парсинг ячейки начисления
        cell1: "10  4" или "9  95" (месяц и код)
        cell2: "20" (рабочие дни/часы) - может быть пустым
        cell3: "29017.39" (сумма)
        """
        # Извлекаем код из первой ячейки (формат: "месяц код" или просто "код")
        code = None

        # Паттерн для "месяц код": "10  4", "9  95"
        match = re.search(r'(\d+)\s+(\d+)', cell1)
        if match:
            code = match.group(2)  # Берем второе число как код
        else:
            # Просто число
            match = re.match(r'^\s*(\d+)\s*$', cell1)
            if match:
                code = match.group(1)

        if not code:
            return None

        # Извлекаем сумму из cell2 или cell3
        amount = None
        for cell in [cell3, cell2]:
            if cell:
                # Очищаем и пробуем преобразовать в число
                amount_str = cell.replace(' ', '').replace(',', '.')
                # Убираем все кроме цифр и точки
                amount_str = re.sub(r'[^\d.]', '', amount_str)
                if amount_str:
                    try:
                        amount = Decimal(amount_str)
                        if amount > 0:
                            break
                    except InvalidOperation:
                        continue

        if code and amount and amount > 0:
            return {
                'code': code,
                'amount': amount,
                'is_deduction': False
            }

        return None

    @staticmethod
    def _parse_deduction_cell(cell1: str, cell2: str) -> Optional[Dict]:
        """
        Парсинг ячейки удержания
        cell1: "10 700" (месяц и код)
        cell2: "16462.38" (сумма)
        """
        code = None

        # Паттерн для "месяц код": "10 700"
        match = re.search(r'(\d+)\s+(\d+)', cell1)
        if match:
            code = match.group(2)
        else:
            match = re.match(r'^\s*(\d+)\s*$', cell1)
            if match:
                code = match.group(1)

        if not code:
            return None

        # Извлекаем сумму
        amount = None
        if cell2:
            amount_str = cell2.replace(' ', '').replace(',', '.')
            amount_str = re.sub(r'[^\d.]', '', amount_str)
            if amount_str:
                try:
                    amount = Decimal(amount_str)
                except InvalidOperation:
                    pass

        if code and amount and amount > 0:
            return {
                'code': code,
                'amount': amount,
                'is_deduction': True
            }

        return None

    @staticmethod
    def _parse_simple_format(content: str) -> List[Dict]:
        """Парсинг простого формата код - сумма"""
        entries = []
        lines = content.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Пробуем разные разделители
            for sep in [' - ', ' – ', ' — ', ':', '\t', '  ']:
                if sep in line:
                    parts = line.split(sep)
                    if len(parts) >= 2:
                        code = parts[0].strip()
                        amount_str = parts[-1].strip()

                        # Очистка суммы
                        amount_str = re.sub(r'[^\d,.\s]', '', amount_str)
                        amount_str = amount_str.replace(' ', '').replace(',', '.')

                        try:
                            amount = Decimal(amount_str)
                            if amount > 0 and len(code) <= 20:
                                entries.append({
                                    'code': code,
                                    'amount': amount,
                                    'is_deduction': False
                                })
                                break
                        except:
                            continue

            # Regex паттерны
            patterns = [
                r'([A-Za-zА-Яа-я0-9_\.]+)\s*[-–—:]\s*([\d\s,.]+)',
                r'(\d+)\s+([\d\s,.]+)',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, line)
                for match in matches:
                    code = match[0].strip()
                    amount_str = match[1].strip().replace(' ', '').replace(',', '.')
                    try:
                        amount = Decimal(amount_str)
                        if amount > 0 and len(code) <= 20:
                            if not any(e['code'] == code for e in entries):
                                entries.append({
                                    'code': code,
                                    'amount': amount,
                                    'is_deduction': False
                                })
                    except:
                        continue

        return entries

    @staticmethod
    def parse_txt_file(file_path: str) -> List[Dict]:
        """Парсинг TXT файла квитанции"""
        encodings = ['utf-8', 'cp1251', 'cp866', 'latin-1', 'koi8-r']
        content = None

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                print(f"[DEBUG] Квитанция прочитана с кодировкой: {encoding}")
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            return []

        return ReceiptParser.parse_receipt_text(content)
class ReceiptOCR:
    """OCR обработка изображений квитанций"""

    @staticmethod
    def extract_text_from_image(file_path: str) -> str:
        """Извлечение текста из изображения"""
        if not TESSERACT_AVAILABLE:
            raise ImportError("pytesseract не установлен. Установите: pip install pytesseract pillow")

        image = Image.open(file_path)

        # Предобработка изображения для лучшего распознавания
        if image.mode != 'L':
            image = image.convert('L')

        # Распознавание текста (русский + английский)
        try:
            text = pytesseract.image_to_string(image, lang='rus+eng')
        except:
            text = pytesseract.image_to_string(image)

        return text

    @staticmethod
    def extract_text_from_pdf(file_path: str) -> str:
        """Извлечение текста из PDF (с OCR если нужно)"""
        if not PYPDF2_AVAILABLE:
            raise ImportError("PyPDF2 не установлен")

        text = ""
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        # Если текст не извлечен, пробуем OCR
        if not text.strip() and PDF2IMAGE_AVAILABLE and TESSERACT_AVAILABLE:
            images = pdf2image.convert_from_path(file_path)
            for image in images:
                try:
                    text += pytesseract.image_to_string(image, lang='rus+eng') + "\n"
                except:
                    text += pytesseract.image_to_string(image) + "\n"

        return text

    @staticmethod
    def parse_receipt_data(text: str) -> List[Dict]:
        """Парсинг данных из распознанного текста квитанции"""
        return ReceiptParser.parse_receipt_text(text)
class PayrollAnalytics:
    """Аналитика платежных ведомостей"""

    @staticmethod
    def get_period_summary(entries) -> Dict:
        """Сводка по периоду"""
        from django.db.models import Sum

        total = entries.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Группировка по категориям/описаниям
        categories = {}
        for entry in entries:
            if entry.payment_code:
                key = entry.payment_code.description
                category = entry.payment_code.category or 'Без категории'
            else:
                key = f"Код {entry.raw_code}"
                category = 'Нераспознанные'

            if category not in categories:
                categories[category] = {'items': {}, 'total': Decimal('0')}

            if key not in categories[category]['items']:
                categories[category]['items'][key] = Decimal('0')

            categories[category]['items'][key] += entry.amount
            categories[category]['total'] += entry.amount

        return {
            'total': total,
            'categories': categories,
            'entries_count': entries.count()
        }

    @staticmethod
    def get_comparison_data(period1_entries, period2_entries) -> Dict:
        """Сравнение двух периодов"""
        summary1 = PayrollAnalytics.get_period_summary(period1_entries)
        summary2 = PayrollAnalytics.get_period_summary(period2_entries)

        diff = summary1['total'] - summary2['total']
        percent_change = 0
        if summary2['total'] > 0:
            percent_change = float((diff / summary2['total']) * 100)

        return {
            'period1_total': summary1['total'],
            'period2_total': summary2['total'],
            'difference': diff,
            'percent_change': round(percent_change, 2)
        }

    @staticmethod
    def get_trend_data(periods_with_entries: List) -> Dict:
        """Данные для графика трендов"""
        labels = []
        totals = []
        categories_data = {}

        for period, entries in periods_with_entries:
            labels.append(str(period))
            summary = PayrollAnalytics.get_period_summary(entries)
            totals.append(float(summary['total']))

            for cat_name, cat_data in summary['categories'].items():
                if cat_name not in categories_data:
                    categories_data[cat_name] = []
                categories_data[cat_name].append(float(cat_data['total']))

        return {
            'labels': labels,
            'totals': totals,
            'categories': categories_data
        }

    @staticmethod
    def get_pie_chart_data(entries) -> Dict:
        """Данные для круговой диаграммы"""
        summary = PayrollAnalytics.get_period_summary(entries)

        labels = []
        values = []
        colors = [
            '#00f5ff', '#ff00ff', '#00ff88', '#ffff00',
            '#ff6b6b', '#4ecdc4', '#a29bfe', '#fd79a8',
            '#ffeaa7', '#74b9ff', '#55efc4', '#fab1a0'
        ]

        for cat_name, cat_data in summary['categories'].items():
            labels.append(cat_name)
            values.append(float(cat_data['total']))

        return {
            'labels': labels,
            'values': values,
            'colors': colors[:len(labels)]
        }
