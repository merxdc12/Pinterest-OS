"""Offline user guide, practical lessons and safe diagnostics."""
from __future__ import annotations

from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTabWidget, QPlainTextEdit,
    QPushButton, QComboBox, QHBoxLayout, QCheckBox, QScrollArea,
    QProgressBar, QFrame,
)

GUIDES = {
    "FILE": "Create a product and set its destination URL. Save a project and make a full ZIP backup before major imports.",
    "PIN": "",
    "BOARD": "Create boards with accurate names and descriptions. Review SEO warnings; they are guidance, not ranking guarantees.",
    "CALENDAR": "Plan publishing slots. A planned slot does not mean a pin was posted.",
    "PUBLISHING": "Open Pinterest in your browser, publish manually, then confirm the outcome in the app. No Pinterest API or auto-posting.",
    "ANALYTICS": "Import measured Pinterest metrics with local pin IDs. Imported numbers are user-provided, not independently verified.",
    "REPORTS": "Inspect product estimates and reconciliation warnings. Estimated contribution is NOT verified net profit.",
    "TIME": "Start/pause/stop the session using the main window. Assign task and pin to future tracked time.",
    "SETTINGS": "Configure appearance and optionally authorize Google Sheets. Review imports before accepting. Google exports create NEW tabs.",
    "HELP": "Read the guide, complete the exercise, and run local diagnostics. Diagnostics never modify records.",
}

LESSONS = (
    ("1. Prepare", "In FILE create a product with a working destination URL. In BOARD create a relevant board. Verify both records."),
    ("2. Produce", "In PIN create a DRAFT linked to that product and board. Check image, title, description and destination."),
    ("3. Plan", "In CALENDAR schedule a slot. Confirm that it remains only a plan until you publish."),
    ("4. Publish manually", "In PUBLISHING open Pinterest, post manually, then record the result. Never mark an unverified post as published."),
    ("5. Measure", "Import actual metrics in ANALYTICS, review estimated contribution in REPORTS, and check time cost in TIME."),
    ("6. Protect", "Create a project backup in FILE. If using Google Sheets, export to a new worksheet and verify the row count."),
)


PIN_GUIDE = """ITHutir Pinterest OS — ПОКРОКОВИЙ ЧЕК-ЛИСТ СТВОРЕННЯ ПІНА

МЕТА
Створити якісний Pinterest-пін, заповнити SEO-метадані, прив'язати дошку
та продукт (за потреби), зберегти дизайн і підготувати до публікації.
ПРИНЦИП: один пін → одна конкретна ціль → одна цільова сторінка.

1. СХЕМА ВЗАЄМОДІЇ
Ідея + аудиторія + цільова сторінка
  ↓
Pinterest OS → PIN → Pin Designer
  ↓
Дизайн: шаблон → зображення → текст → перевірка читабельності
  ↓
SEO: заголовок → опис → теги → Destination URL
  ↓
Board + Status (DRAFT) + Product (необов'язково)
  ↓
ЗБЕРЕГТИ ПІН → SQLite + PNG у PINTEREST_PIN
  ↓
Preview → перевірка PNG, URL, PIN ID та відповідності дошці
  ↓
READY → ручна публікація у Pinterest → перевірка → PUBLISHED
  ↘
   Google Sheets: окремий EXPORT / СИНХРОНІЗУВАТИ

2. ПРАКТИЧНИЙ ПРИКЛАД (АНГЛОМОВНИЙ РИНОК)
Тема: Home Server Setup Guide.
Аудиторія: Linux, Homelab, Self-Hosting.
Мета: цільовий перехід на відповідну статтю чи інструмент ITHutir.
Дошка: Linux, Homelab & Self-Hosting.
Продукт: залишити порожнім для безкоштовної навчальної статті.
Візуальні приклади сторонніх сайтів — лише орієнтири; перевіряйте права
на використання кожного зображення.

3. ПОКРОКОВА ПРАКТИКА
ПІДГОТОВКА:
01. Визначте тему, конкретну аудиторію й одну вимірювану мету.
02. Перевірте, що цільова сторінка існує та відповідає обіцянці піна.
03. Підготуйте власне або ліцензоване зображення.

ДИЗАЙН:
04. Відкрийте Pinterest OS → PIN → Pin Designer.
05. Виберіть шаблон або створіть чистий макет.
06. Натисніть IMPORT Image та виберіть зображення.
07. Додайте заголовок через + Text layer.
08. Налаштуйте шрифт, ЖИРНИЙ / Bold, розмір, контраст, позиції шарів.
    Не перекривайте ключовий зміст і перевірте читабельність на телефоні.

МЕТАДАНІ:
09. Натисніть Create new pin for this design (для нового піна).
10. Введіть Pin title англійською з природним основним запитом.
11. Заповніть Description та Tags без спаму ключовими словами.
12. Введіть повний робочий Destination URL (https://...).
13. Виберіть тематичну дошку Board.
14. Встановіть Status = DRAFT.
15. Виберіть Product лише якщо є відповідний продукт.

ЗБЕРЕЖЕННЯ ТА КОНТРОЛЬ:
16. Натисніть ЗБЕРЕГТИ ПІН (Ctrl+S) біля «Пов'язаний пін».
17. Перевірте присвоєний унікальний PIN ID.
18. Натисніть Preview і перевірте весь макет.
19. Перевірте PNG у PINTEREST_PIN; за потреби скористайтеся
    Export PNG + link to pin та кнопкою ВІДКРИТИ КАТАЛОГ.
20. Перевірте орфографію, URL, відповідність зображення і дошки.
21. Відкрийте PIN → Google Sheets: переконайтеся, що локальний
    збережений рядок присутній. Віддалений запис — окрема дія.

ПУБЛІКАЦІЯ:
22. Після перевірки вручну змініть Status на READY.
23. Опублікуйте пін вручну на потрібній дошці Pinterest.
24. Перевірте реальний пін у Pinterest і перехід за посиланням.
25. Лише після підтвердження вручну встановіть PUBLISHED.

4. ДОВІДНИК ПОЛІВ
Пов'язаний пін — наявний запис для редагування; для нього спочатку
використайте Load pin project. Новий запис створюйте лише один раз.
PIN ID — стабільний локальний ідентифікатор для PNG та Google Sheets.
Pin title — зрозумілий англомовний SEO-заголовок.
Description — користь, зміст і доречний заклик до дії.
Tags — тематичні ключові слова, розділені комами.
Destination URL — повне посилання на відповідну сторінку.
Board — тематична дошка.
Status — ручний стан підготовки, не підтвердження з Pinterest.
Product — необов'язковий зв'язок із локальним каталогом продуктів.

5. ПРИКЛАД SEO-МЕТАДАНИХ
Pin title: Home Server Setup Guide for Beginners
Description: Learn the basics of setting up a home server with Linux.
Explore essential hardware, networking, storage and self-hosting concepts
for your first homelab. Read the complete guide.
Tags: home server, Linux homelab, self-hosting, home lab setup,
beginner server guide
Destination URL: вставте РЕАЛЬНЕ посилання на відповідну статтю.
Ці ключові слова — приклад, а не підтверджені частотні SEO-запити.

6. ПРАВИЛА БЕЗПЕКИ ДАНИХ
ЗБЕРЕГТИ ПІН ≠ публікація в Pinterest.
PNG ≠ публікація в Pinterest.
Локальна таблиця Google Sheets ≠ віддалена Google Таблиця.
EXPORT / СИНХРОНІЗУВАТИ працюють окремо від локального збереження.
PUBLISHED — ручна позначка, встановлюйте її після перевірки публікації.
Не створюйте дублікати під час редагування існуючого піна.
Прапорці чек-листа не змінюють статуси й записи Pinterest OS.

7. КОМЕРЦІЙНИЙ КОНТРОЛЬ
Перед публікацією перевірте:
• Чи є конкретна аудиторія?
• Чи веде пін на корисну та релевантну сторінку?
• Яка вимірювана мета: відвідування, підписка або продаж?
Оцінюйте трафік, конверсію, витрати часу та реальний прибуток,
а не тільки кількість створених пінів. Починайте з одного
повністю перевіреного піна перед масштабуванням.
"""

PIN_CHECKLIST = (
    ("1. Підготовка", (
        "Визначити тему, аудиторію та одну мету піна",
        "Перевірити цільову сторінку та Destination URL",
        "Підготувати власне або дозволене зображення",
    )),
    ("2. Створення дизайну", (
        "Відкрити PIN → Pin Designer",
        "Вибрати шаблон або чистий макет",
        "Додати зображення через IMPORT Image",
        "Додати заголовок через + Text layer",
        "Налаштувати шрифт, жирність, контраст і композицію",
    )),
    ("3. Метадані", (
        "Створити новий пін через Create new pin for this design",
        "Вказати SEO-заголовок Pin title",
        "Заповнити Description та Tags",
        "Вставити перевірений Destination URL",
        "Вибрати дошку Board",
        "Встановити статус DRAFT",
        "Вибрати Product або залишити порожнім",
    )),
    ("4. Збереження та перевірка", (
        "Натиснути ЗБЕРЕГТИ ПІН (Ctrl+S)",
        "Перевірити PIN ID",
        "Перевірити дизайн через Preview",
        "Перевірити PNG у каталозі PINTEREST_PIN",
        "Перевірити PNG, текст, URL і дошку",
        "Перевірити локальний запис у вкладці Google Sheets",
    )),
    ("5. Публікація", (
        "Після перевірки вручну встановити READY",
        "Опублікувати пін вручну в Pinterest",
        "Перевірити публікацію та перехід за посиланням",
        "Після підтвердження вручну встановити PUBLISHED",
    )),
)

GUIDES["PIN"] = PIN_GUIDE

def diagnostics(storage):
    """Read-only SQLite checks; no external network requests."""
    conn = storage.conn
    result = []
    quick = conn.execute("PRAGMA quick_check").fetchone()
    result.append("SQLite quick_check: " + (str(quick[0]) if quick else "UNKNOWN"))
    foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    result.append(f"Foreign key violations: {len(foreign_keys)}")
    for table in ("products", "boards", "pins", "pin_schedule",
                  "pinterest_metrics", "time_entries"):
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            result.append(f"{table}: {count}")
        except Exception as exc:
            result.append(f"{table}: unavailable ({type(exc).__name__})")
    path = Path(storage.path)
    result.append(f"Database file exists: {path.is_file()}")
    result.append("No backup created; no external Google or Pinterest connectivity tested.")
    return "\n".join(result)


class HelpPage(QWidget):
    def __init__(self, storage, parent=None):
        super().__init__(parent)
        self.storage = storage
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Offline guidance for organic Pinterest workflows. "
            "No publishing automation, paid ads, or verified revenue claims."))
        tabs = QTabWidget()
        layout.addWidget(tabs)

        guide = QWidget()
        guide_layout = QVBoxLayout(guide)
        selector_row = QHBoxLayout()
        self.guide_selector = QComboBox()
        self.guide_selector.addItems(GUIDES)
        self.guide_selector.currentTextChanged.connect(self.show_guide)
        selector_row.addWidget(QLabel("Module"))
        selector_row.addWidget(self.guide_selector)
        guide_layout.addLayout(selector_row)
        self.guide_text = QPlainTextEdit()
        self.guide_text.setReadOnly(True)
        guide_layout.addWidget(self.guide_text)
        tabs.addTab(guide, "User Guide")
        pin_help = QWidget()
        pin_help_layout = QVBoxLayout(pin_help)
        pin_help_layout.addWidget(QLabel(
            "ПІН — практичний чек-лист (25 кроків). "
            "Позначки не змінюють дані програми."))
        self.pin_check_progress = QProgressBar()
        self.pin_check_progress.setRange(0, 25)
        pin_help_layout.addWidget(self.pin_check_progress)
        self.pin_check_count = QLabel("0 із 25 кроків виконано")
        pin_help_layout.addWidget(self.pin_check_count)
        pin_scroll = QScrollArea()
        pin_scroll.setWidgetResizable(True)
        pin_inner = QWidget()
        pin_inner_layout = QVBoxLayout(pin_inner)
        self.pin_checkboxes = []
        for heading, tasks in PIN_CHECKLIST:
            section = QLabel(heading)
            section.setStyleSheet("font-weight: 700; margin-top: 12px;")
            pin_inner_layout.addWidget(section)
            for task in tasks:
                check = QCheckBox(task)
                check.toggled.connect(self.update_pin_check_progress)
                self.pin_checkboxes.append(check)
                pin_inner_layout.addWidget(check)
        pin_inner_layout.addStretch()
        pin_scroll.setWidget(pin_inner)
        pin_help_layout.addWidget(pin_scroll)
        reset = QPushButton("СКИНУТИ ПОЗНАЧКИ")
        reset.clicked.connect(self.reset_pin_checklist)
        pin_help_layout.addWidget(reset)
        tabs.addTab(pin_help, "ПІН — чек-лист")

        lessons = QWidget()
        lessons_layout = QVBoxLayout(lessons)
        self.lesson_selector = QComboBox()
        for name, _ in LESSONS:
            self.lesson_selector.addItem(name)
        self.lesson_selector.currentIndexChanged.connect(self.show_lesson)
        lessons_layout.addWidget(self.lesson_selector)
        self.lesson_text = QPlainTextEdit()
        self.lesson_text.setReadOnly(True)
        lessons_layout.addWidget(self.lesson_text)
        tabs.addTab(lessons, "Practical Learning")

        checks = QWidget()
        checks_layout = QVBoxLayout(checks)
        checks_layout.addWidget(QLabel(
            "Read-only diagnostics. They do not validate external services or replace backups."))
        self.diagnostic_text = QPlainTextEdit()
        self.diagnostic_text.setReadOnly(True)
        checks_layout.addWidget(self.diagnostic_text)
        button = QPushButton("Run local diagnostics")
        button.clicked.connect(self.run_diagnostics)
        checks_layout.addWidget(button)
        tabs.addTab(checks, "Diagnostics")

        trouble = QPlainTextEdit()
        trouble.setReadOnly(True)
        trouble.setPlainText(
            "Google Sheets: OAuth requires a local desktop-client JSON and an unlocked OS keyring. "
            "Never commit credentials.\n\n"
            "Duplicate import: review the source and existing local records; do not bypass conflict checks.\n\n"
            "Missing metrics: verify local pin IDs, date format YYYY-MM-DD, and nonnegative counts.\n\n"
            "Database error: stop editing, preserve the project, create a backup, and inspect diagnostics.\n\n"
            "Publishing status: only confirm after verifying the actual Pinterest post in the browser.\n\n"
            "Revenue: use attributable evidence and reconcile all costs before treating an estimate as profit.")
        tabs.addTab(trouble, "Troubleshooting")
        self.show_guide()
        self.show_lesson()
        self.run_diagnostics()

    def update_pin_check_progress(self, *_):
        done = sum(check.isChecked() for check in self.pin_checkboxes)
        self.pin_check_progress.setValue(done)
        self.pin_check_count.setText(f"{done} із 25 кроків виконано")

    def reset_pin_checklist(self):
        for check in self.pin_checkboxes:
            check.setChecked(False)

    def show_guide(self, *_):
        name = self.guide_selector.currentText()
        self.guide_text.setPlainText(name + "\n\n" + GUIDES.get(name, ""))

    def show_lesson(self, *_):
        index = self.lesson_selector.currentIndex()
        if index >= 0:
            title, body = LESSONS[index]
            self.lesson_text.setPlainText(
                title + "\n\n" + body +
                "\n\nCheckpoint: perform the action in the app and verify the saved result.")

    def run_diagnostics(self):
        try:
            self.diagnostic_text.setPlainText(diagnostics(self.storage))
        except Exception as exc:
            self.diagnostic_text.setPlainText(
                f"Diagnostic failed: {type(exc).__name__}: {exc}")

    def set_storage(self, storage):
        self.storage = storage
        self.run_diagnostics()
