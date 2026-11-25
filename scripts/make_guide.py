"""Создание учебного PDF. Отдельный инструмент документации, не часть MCP-сервера.
Нужен reportlab==4.4.9. Запуск: python -m scripts.make_guide.
"""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "tutu-mcp-guide.pdf"
BLUE = colors.HexColor("#174B72")
INK = colors.HexColor("#192C3B")
MUTED = colors.HexColor("#516572")
PALE = colors.HexColor("#EAF2F7")


def fonts():
    mac = Path('/System/Library/Fonts/Supplemental')
    linux = Path('/usr/share/fonts/truetype/dejavu')
    paths = (mac/'Arial.ttf', mac/'Arial Bold.ttf', mac/'Courier New.ttf')
    if not paths[0].exists():
        paths = (linux/'DejaVuSans.ttf', linux/'DejaVuSans-Bold.ttf', linux/'DejaVuSansMono.ttf')
    for name, path in zip(['Body', 'Bold', 'Mono'], paths):
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Body', boldItalic='Bold')


def build():
    fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = {
        'title': ParagraphStyle('title', fontName='Bold', fontSize=31, leading=36, textColor=INK, spaceAfter=17),
        'h1': ParagraphStyle('h1', fontName='Bold', fontSize=23, leading=29, textColor=INK, spaceAfter=15),
        'h2': ParagraphStyle('h2', fontName='Bold', fontSize=13, leading=18, textColor=BLUE, spaceBefore=13, spaceAfter=6),
        'body': ParagraphStyle('body', fontName='Body', fontSize=10.5, leading=16, textColor=INK, spaceAfter=9),
        'small': ParagraphStyle('small', fontName='Body', fontSize=9, leading=13, textColor=MUTED, spaceAfter=7),
        'code': ParagraphStyle('code', fontName='Mono', fontSize=8.5, leading=13, textColor=INK, spaceAfter=8),
        'label': ParagraphStyle('label', fontName='Bold', fontSize=9, leading=13, textColor=BLUE, spaceAfter=12),
    }
    story = []
    def p(text, kind='body'):
        story.append(Paragraph(text, styles[kind]))
    def heading(label, title):
        p(label, 'label');p(title, 'h1')
    def section(title, text):
        p(title, 'h2');p(text)
    def code(text):
        p(escape(text).replace(' ', '&nbsp;').replace('\n', '<br/>'), 'code')
    def note(text):
        table = Table([[Paragraph(text, styles['body'])]], colWidths=[170*mm])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
        story.extend([table, Spacer(1,9)])
    def new():story.append(PageBreak())

    p('УЧЕБНЫЙ ПРОЕКТ / PYTHON / MCP', 'label')
    p('Как устроен<br/>tutu-mcp', 'title')
    p('Понятный путеводитель по коду для тех, кто впервые видит проект.', 'body')
    note('<b>Что делает проект:</b> помогает агенту Codex найти прямые поезда на Туту, открыть вагоны и прочитать доступные места и цены. Покупка и бронирование в проект не входят.')
    section('Сначала - пять участников', 'Пользователь пишет обычную фразу. Codex понимает маршрут, дату и пожелания. MCP передаёт вызов функции нашему серверу. Playwright управляет Chrome. Сайт Туту показывает реальные предложения.')
    labels=['Пользователь','Codex','Python MCP','Playwright','Туту']
    cells=[[Paragraph(f'<b>{x}</b>', styles['small']) for x in labels]]
    table=Table(cells,colWidths=[34*mm]*5)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('GRID',(0,0),(-1,-1),0.5,colors.white),('LEFTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.extend([table,Spacer(1,10)])
    p('Запрос идёт слева направо. Данные и результаты возвращаются обратно.', 'small')
    section('Пример', '«Найди Москва - Казань на 15 декабря 2026 года, купе, нижнее место до 6000 рублей». Codex превращает эту фразу в параметры, вызывает инструменты и сравнивает найденные места с условиями.')
    section('Главная мысль', 'Сам Python-сервер не является нейросетью. Он выполняет конкретные действия и возвращает данные. Понимание текста и итоговый ответ пользователю обеспечивает Codex.')
    p('Версия объяснения: Python-реализация 0.2.0, 25 ноября 2026 года. Примеры дат и цен не являются актуальными предложениями билетов.', 'small')

    new();heading('01 / ВХОД В ПРОЕКТ', 'Где начинается работа')
    section('server.py в корне', 'Очень короткая точка входа: импортирует main из tutu_mcp/server.py и запускает его. Именно этот файл указан в конфигурации Codex. Основная логика находится в пакете tutu_mcp, а не в этом коротком файле.')
    section('tutu_mcp/server.py', 'Создаёт MCP-сервер, регистрирует три инструмента, проверяет входные параметры и упаковывает результат или ошибку. Здесь также настроены завершение процесса и закрытие браузера.')
    code('@server.tool(annotations=annotations, structured_output=False)\nasync def search_trains(origin, destination, departure_date):\n    return await invoke(lambda: adapter.search(\n        origin.strip(), destination.strip(), departure_date\n    ))')
    p('Код выше сокращён для объяснения. В исходнике есть аннотации типов и описание инструмента.', 'small')
    section('Что означает каждая часть', '<b>@server.tool(...)</b> сообщает SDK: эту функцию можно вызвать через MCP.<br/><b>async def</b> позволяет ждать сайт и браузер без блокирования всего цикла событий.<br/><b>origin / destination / departure_date</b> - структурированные параметры, которые передаёт агент.<br/><b>invoke(...)</b> возвращает ответ в формате MCP или понятную ошибку.<br/><b>adapter.search(...)</b> запускает реальный сценарий на сайте.')
    note('Строка «Найти прямые поезда...» в docstring - описание для агента. Она сама не выполняет поиск. Поиск происходит только при вызове adapter.search().')
    section('Что такое MCP и stdio', 'MCP - общий протокол: какие инструменты существуют, какие у них параметры и что они вернули. SDK берёт на себя обмен сообщениями. stdio означает, что Codex общается с отдельным процессом сервера через его стандартный ввод и вывод. Поэтому обычные логи пишутся в stderr, а не stdout.')

    new();heading('02 / САЙТ И БРАУЗЕР', 'Где реально ищутся билеты')
    section('tutu_mcp/tutu.py - адаптер Туту', 'Это главный файл взаимодействия с сайтом. Он знает элементы формы, порядок действий, способ чтения карточек поездов и схему мест. Все локаторы - признаки, по которым Playwright находит элементы страницы, - собраны здесь.')
    section('search() - поиск поездов', 'Проверяет дату, открывает Туту, выбирает города через подсказки, выбирает день в календаре и нажимает поиск. Затем догружает список, читает прямые поезда и создаёт result_id для каждого. Пересадки не подбираются.')
    section('seats() - список вагонов', 'По result_id находит сохранённый поезд, снова открывает живую страницу и переходит к выбору мест. Возвращает номера вагонов, типы, количество доступных мест и услуги.')
    section('carriage() - конкретные места', 'Раскрывает выбранный вагон. Читает номера и состояния мест, проверяет их количество, связывает места с группами купе, тарифами и классами обслуживания. Этот результат нужен для пожелания «нижнее место» или «в одном купе».')
    section('tutu_mcp/browser.py - управление Chrome', 'Запускает Playwright и Chrome, создаёт временные контексты и закрывает их. Личный профиль пользователя не подключается. asyncio.Lock не даёт запросам одновременно вмешиваться в действия браузера. Режим HEADED=1 показывает окно для отладки.')
    note('<b>Если Туту изменит интерфейс:</b> сначала смотрите tutu_mcp/tutu.py. Неверный локатор или новая разметка могут сломать поиск, хотя сам MCP продолжает нормально передавать вызовы.')
    p('В файле есть небольшие JavaScript-выражения для чтения DOM внутри браузера. Это обычная часть Playwright Python; отдельного Node.js-сервера в проекте нет.', 'small')

    new();heading('03 / ДАННЫЕ И ДОСТОВЕРНОСТЬ', 'Почему нельзя просто читать цифры')
    section('tutu_mcp/parsers.py - перевод данных', 'Превращает текст и структуры сайта в понятные поля. Например, строку «от 4 017 руб.» превращает в число и валюту. Сохраняет переход даты у ночного поезда и отделяет верхнюю полку от нижней по данным схемы.')
    section('normalize_seats() - отбор свободных мест', 'Берёт только элементы с data-ti-state=active. Серые занятые места на схеме тоже имеют номера, но в результат не включаются. Тип полки берётся из data-ti-type, а не вычисляется по чётности номера.')
    section('Как определяется цена', 'Обычный взрослый тариф выбирается отдельно от детского и условной платёжной скидки. Цена относится к группе конкретного места. Минимальная цена всего вагона не присваивается каждой полке. При неоднозначности возвращается null.')
    section('tutu_mcp/models.py - описание структуры', 'Pydantic-модели описывают цену, место, вагон, группу мест, тариф и участок маршрута. Они проверяют, что публичные данные страницы имеют ожидаемую структуру. Если структура изменилась, безопаснее вернуть ошибку, чем выдать неверные места.')
    section('Откуда берётся подробная информация', 'Сначала из отрисованной страницы, а для купе, классов и тарифов также из публичного блока __NEXT_DATA__, который получает сама страница. Это недокументированный формат Туту, а не официальный API сервиса.')
    note('<b>Что пока неизвестно:</b> этаж и пол купе возвращаются null. Не все перевозчики и схемы проверены. В ответах сохраняются checked_at и предупреждения: наличие и цены могут измениться до оформления.')

    new();heading('04 / АГЕНТ, НАСТРОЙКИ, ОШИБКИ', 'Кто принимает решения')
    section('AGENTS.md - инструкция для Codex', 'Объясняет агенту, как понять русскую фразу, перевести «завтра» в дату, уточнить недостающее и выбрать до пяти вариантов. При пожелании конкретной полки требует открыть вагоны и места. Запрещает покупку, бронирование и ввод личных данных.')
    section('.codex/config.toml - локальное подключение', 'Содержит команду запуска Python и абсолютный путь server.py. Codex запускает процесс сам. Этот файл зависит от компьютера и не публикуется в Git. Для друзей в репозитории лежит codex-config.example.toml - его нужно скопировать и заменить пути.')
    section('tutu_mcp/errors.py - ошибки и даты', 'Проверяет существование даты и то, что день не прошёл в часовом поясе пользователя. TutuError хранит код, сообщение и подробности. Сервер различает устаревший результат, ошибку загрузки, изменение сайта и другие ситуации.')
    section('Зачем нужен result_id', 'UUID связывает поезд, маршрут и дату в памяти процесса. Живёт 15 минут. После перезапуска сервера старые идентификаторы не работают: нужно снова вызвать search_trains. Это не номер заказа и не бронь.')
    section('Примеры ошибок', '<b>PAST_DATE</b> - дата прошла.<br/><b>AMBIGUOUS_STATION</b> - надо уточнить станцию.<br/><b>STALE_RESULT</b> - повторить поиск.<br/><b>BLOCKED</b> - сайт ограничил доступ, обход не выполняется.<br/><b>TIMEOUT / SITE_CHANGED</b> - данные не удалось надёжно прочитать.')
    note('Ошибка загрузки не равна отсутствию мест. Нельзя писать «всё распродано», если сайт просто не ответил. Причина отсутствия предложений устанавливается только по фактическим данным.')

    new();heading('05 / ПРОВЕРКИ И ПЕРВЫЙ ЗАПУСК', 'Как разобраться самому')
    section('tests/test_parsers.py и tests/fixtures/', 'pytest проверяет цены, даты, доступность и реальные сохранённые примеры схем. fixtures - исторические тестовые снимки. Сервер никогда не подставляет их вместо живых предложений.')
    section('scripts/ - проверочные программы', '<b>client.py</b> запускает отдельный сервер через настоящий MCP-клиент.<br/><b>smoke.py</b> проверяет список инструментов и отрицательные сценарии.<br/><b>live.py</b> проверяет два маршрута, вагоны, места и нижние полки до бюджета.<br/><b>verify_ui.py</b> сверяет три места и цены с интерфейсом.<br/><b>make_guide.py</b> создаёт этот PDF; нужен только для документации.')
    section('Остальные файлы', '<b>README.md</b> - установка, подключение и ограничения.<br/><b>pyproject.toml</b> - описание Python-пакета и прямые зависимости.<br/><b>requirements.lock</b> - точные версии библиотек.<br/><b>.gitignore</b> - что не должно попадать в Git.<br/><b>.venv/</b> - установленный Python и библиотеки; создаётся локально.<br/><b>artifacts/</b> - JSON и снимки проверок; не исходники.<br/><b>docs/live-verification.md</b> - отчёт о фактически проведённой проверке.')
    section('Минимальные команды после клонирования', 'Нужны Python 3.11+ и Google Chrome. Выполняйте команды из папки проекта. Для Windows путь к Python в окружении отличается.')
    code('python3 -m venv .venv\n.venv/bin/python -m pip install -r requirements.lock\n.venv/bin/python -m pytest -q\n.venv/bin/python -m scripts.smoke')
    p('Затем настройте Codex по codex-config.example.toml и откройте новый чат. Вручную запускать сервер для обычного использования не нужно. Для отладки: .venv/bin/python server.py.', 'small')
    note('<b>Порядок чтения кода:</b> server.py в корне, затем tutu_mcp/server.py, tutu_mcp/tutu.py, parsers.py и models.py. После этого browser.py, errors.py и тесты. Репозиторий: github.com/ogwayz/tutu-mcp')

    def page(canvas, doc):
        canvas.setTitle('Как устроен tutu-mcp')
        canvas.setAuthor('tutu-mcp project')
        canvas.setStrokeColor(colors.HexColor('#D8E3EB'))
        canvas.line(20*mm, 20*mm,190*mm,20*mm)
        canvas.setFont('Body',8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20*mm,14*mm,'TUTU-MCP  /  PYTHON  /  ПУТЕВОДИТЕЛЬ ПО КОДУ')
        canvas.drawRightString(190*mm,14*mm,str(doc.page))
    doc=SimpleDocTemplate(str(OUTPUT),pagesize=(210*mm,297*mm),leftMargin=20*mm,rightMargin=20*mm,topMargin=20*mm,bottomMargin=27*mm)
    doc.build(story,onFirstPage=page,onLaterPages=page)
    return OUTPUT


if __name__ == '__main__':
    print(build())
