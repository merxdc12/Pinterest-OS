"""Ukrainian UI text catalog; source strings are canonical English keys."""
from PyQt6.QtCore import QSettings, QLibraryInfo, QTranslator
from PyQt6.QtWidgets import QApplication, QPushButton, QLabel, QGroupBox, QTabWidget, QComboBox, QLineEdit, QCheckBox, QRadioButton

UK = {'FILE': 'ФАЙЛ', 'PIN': 'ПІН', 'CONTENT FACTORY': 'ФАБРИКА КОНТЕНТУ', 'BOARD': 'ДОШКИ', 'CALENDAR': 'КОНТЕНТ-ПЛАН', 'PUBLISHING': 'ПУБЛІКАЦІЯ', 'ANALYTICS': 'АНАЛІТИКА', 'REPORTS': 'ЗВІТИ', 'TIME': 'ЧАС', 'SETTINGS': 'НАЛАШТУВАННЯ', 'HELP': 'ДОВІДКА', 'Pin Library / CSV': 'Бібліотека пінів / CSV', 'Google Sheets': 'Google Таблиці', 'Pin Designer': 'Редактор пінів', 'Free Image Library': 'Бібліотека зображень', 'CANVA': 'CANVA', 'Carousel Builder': 'Конструктор каруселей', 'Workspace': 'Робочий простір', 'Pin library': 'Бібліотека пінів', 'Boards': 'Дошки', 'Publishing': 'Публікація', 'Settings': 'Налаштування', 'Help': 'Довідка', 'Appearance': 'Вигляд', 'Accounts': 'Облікові записи', 'Diagnostics': 'Діагностика', 'System': 'Системна', 'Dark': 'Темна', 'Light': 'Світла', 'Application color theme': 'Колірна тема програми', 'Linked pin': "Пов'язаний пін", 'Create new pin': 'СТВОРИТИ НОВИЙ ПІН', 'Create new pin for this design': 'Створити пін для цього дизайну', 'Load pin project': 'Завантажити проєкт піна', 'Template': 'Шаблон', 'Apply template': 'Застосувати шаблон', '+ Text layer': '+ Текстовий шар', 'IMPORT Image': 'ІМПОРТ зображення', 'Selected text': 'Вибраний текст', 'Font': 'Шрифт', 'Font size': 'Розмір шрифту', 'Alignment': 'Вирівнювання', 'Text color': 'Колір тексту', 'Bring forward': 'На передній план', 'Send backward': 'На задній план', 'Delete selected layer': 'Видалити вибраний шар', 'Layers (top first)': 'Шари (верхні першими)', 'X position': 'Позиція X', 'Y position': 'Позиція Y', 'Image size': 'Розмір зображення', 'Zoom': 'Масштаб', 'Preview at canvas size': 'Перегляд у розмірі полотна', 'Save editable project': 'Зберегти редагований проєкт', 'Export PNG + link to pin': "Експорт PNG і прив'язка до піна", 'Saved / no pending changes': 'Збережено / немає змін', 'Open Canva Templates': 'Відкрити шаблони Canva', 'IMPORT OF CANVA': 'ІМПОРТ із Canva', 'EXPOT_in_CANVAS': 'ЕКСПОРТ у Canva', 'Canva design ID': 'ID дизайну Canva', 'Link Canva design to pin': "Прив'язати дизайн Canva до піна", 'Search free images': 'Пошук безкоштовних зображень', 'IMPORT Image → Pin Designer': 'Імпорт зображення → Редактор пінів', 'Source': 'Джерело', 'Search images': 'Пошук зображень', 'Search free images in browser': 'Пошук зображень у браузері', 'Import downloaded image → Pin Designer': 'Імпорт завантаженого зображення → Редактор', 'Save account identifiers': 'Зберегти дані облікових записів', 'Pinterest email': 'Пошта Pinterest', 'Google email': 'Пошта Google', 'Pinterest profile URL': 'Адреса профілю Pinterest', 'Spreadsheet URL': 'Адреса таблиці', 'Validate and save link': 'Перевірити та зберегти посилання', 'Preview public sheet (read-only)': 'Перегляд публічної таблиці (лише читання)', 'Open Pinterest sign-in in browser': 'Відкрити вхід Pinterest у браузері', 'Open Google Drive in browser': 'Відкрити Google Диск у браузері', 'Open Canva': 'Відкрити Canva', 'Title': 'Назва', 'Description': 'Опис', 'Status': 'Статус', 'Board': 'Дошка', 'Product': 'Продукт', 'Destination URL': 'Цільове посилання (URL) товару', 'Save': 'Зберегти', 'Cancel': 'Скасувати', 'Delete': 'Видалити', 'Add': 'Додати', 'Edit': 'Редагувати', 'Export': 'Експорт', 'Import': 'Імпорт', 'Refresh': 'Оновити', 'Search': 'Пошук', 'Close': 'Закрити', 'Create': 'Створити', 'Open': 'Відкрити', 'Preview': 'Перегляд', 'Pause': 'Пауза', 'Stop session': 'Завершити сеанс', 'Pin title:': 'Назва піна:', 'Language': 'Мова', 'English': 'Англійська', 'Українська': 'Українська'}

def apply_language(root, language=None):
    lang = language or QSettings("ITHutir", "PinterestOS").value("appearance/language", "en", str)
    # Qt's own standard buttons (Yes/No/OK/Cancel) follow the chosen UI language.
    app = QApplication.instance()
    if app is not None:
        current = getattr(app, "_ithutir_qt_translator", None)
        if lang == "uk" and current is None:
            translator = QTranslator(app)
            path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
            if translator.load("qtbase_uk", path):
                app.installTranslator(translator)
                app._ithutir_qt_translator = translator
        elif lang != "uk" and current is not None:
            app.removeTranslator(current)
            app._ithutir_qt_translator = None
    for widget in [root, *root.findChildren(QPushButton), *root.findChildren(QLabel), *root.findChildren(QGroupBox), *root.findChildren(QTabWidget), *root.findChildren(QComboBox), *root.findChildren(QLineEdit), *root.findChildren(QCheckBox), *root.findChildren(QRadioButton)]:
        if isinstance(widget, QTabWidget):
            for i in range(widget.count()):
                key = widget.tabBar().tabData(i)
                if key is None:
                    key = widget.tabText(i)
                    widget.tabBar().setTabData(i, key)
                widget.setTabText(i, UK.get(key, key) if lang == "uk" else key)
        elif isinstance(widget, QComboBox):
            for i in range(widget.count()):
                key = widget.itemData(i, 257)
                if key is None:
                    key = widget.itemText(i)
                    widget.setItemData(i, key, 257)
                widget.setItemText(i, UK.get(key, key) if lang == "uk" else key)
        elif isinstance(widget, (QPushButton, QLabel, QGroupBox, QCheckBox, QRadioButton)):
            key = widget.property("_i18n_original")
            if key is None:
                key = widget.title() if isinstance(widget, QGroupBox) else widget.text()
                widget.setProperty("_i18n_original", key)
            value = UK.get(key, key) if lang == "uk" else key
            if isinstance(widget, QGroupBox): widget.setTitle(value)
            else: widget.setText(value)
        elif isinstance(widget, QLineEdit):
            key = widget.property("_i18n_placeholder")
            if key is None:
                key = widget.placeholderText()
                widget.setProperty("_i18n_placeholder", key)
            widget.setPlaceholderText(UK.get(key, key) if lang == "uk" else key)
