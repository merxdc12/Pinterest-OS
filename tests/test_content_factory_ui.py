"""Offscreen UI tests of the real Content Factory and reused workspace pages."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from pinterest_os.app import MENU, MainWindow
from pinterest_os.content_factory_page import ContentFactoryPage
from pinterest_os.storage import Storage
from pinterest_os.theme import ThemeManager
from pinterest_os.project_files import create_project


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_tabs_planner_editing_and_project_switch(app, tmp_path):
    first, second = Storage(tmp_path / 'first.sqlite3'), Storage(tmp_path / 'second.sqlite3')
    page = ContentFactoryPage(first)
    try:
        assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == ['Planner', 'Keywords', 'AI SEO', 'Design', 'Review', 'Export']
        page.create_campaign()
        page.create_campaign()
        assert page.plan.rowCount() == page.selected_slot.count() == 12
        source = page.factory.add_source('FREE_TOOL', 'https://ithutir.com/tool', 'Tool')
        board = first.create('boards', name='Tools', url='https://www.pinterest.com/example/tools/')
        page.reload()
        page.source.setCurrentIndex(page.source.findData(source))
        page.board.setCurrentIndex(page.board.findData(board))
        page.kind.setCurrentText('LEAD_GEN')
        page.save_slot()
        assert page.factory.slot(page.slot_id())['board_id'] == board
        assert page.factory.slot(page.slot_id())['content_type'] == 'LEAD_GEN'
        page.set_storage(second)
        assert page.plan.rowCount() == 0
        assert page.source.count() == 1
        assert page.factory.storage is second
    finally:
        page.close()
        first.close()
        second.close()


def test_error_is_user_facing_and_no_export(app, tmp_path):
    db = Storage(tmp_path / 'ui.sqlite3')
    page = ContentFactoryPage(db)
    try:
        with patch.object(QMessageBox, 'warning') as warning:
            page.action(page.export_selected)
        assert 'Create or select' in warning.call_args.args[-1]
        assert db.conn.execute('SELECT COUNT(*) FROM pin_schedule').fetchone()[0] == 0
    finally:
        page.close()
        db.close()


def test_rss_worker_does_not_write_to_switched_workspace(app, tmp_path):
    first, second = Storage(tmp_path / 'one.sqlite3'), Storage(tmp_path / 'two.sqlite3')
    page = ContentFactoryPage(first)
    try:
        old_factory = page.factory
        page.set_storage(second)
        page.feed_loaded(old_factory, [])
        page.feed_failed(old_factory, 'Old request failed')
        assert first.conn.execute('SELECT COUNT(*) FROM content_feed_refresh').fetchone()[0] == 0
        assert second.conn.execute('SELECT COUNT(*) FROM content_feed_refresh').fetchone()[0] == 0
        with patch('pinterest_os.content_factory_page.fetch_feed', return_value=b'<rss><channel/></rss>'):
            page.refresh_feed()
            loop = QEventLoop()
            page.worker.finished.connect(loop.quit)
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            app.processEvents()
            assert not page.worker.isRunning()
        assert second.conn.execute('SELECT status FROM content_feed_refresh').fetchone()[0] == 'OK'
        assert page.feed_button.isEnabled()
    finally:
        if page.worker and page.worker.isRunning():
            page.worker.wait(3000)
        page.close()
        first.close()
        second.close()


def test_main_window_reuses_designer_calendar_and_project_switch(app, tmp_path):
    db = Storage(tmp_path / 'main.sqlite3')
    theme = ThemeManager(app)
    window = MainWindow(db, theme)
    try:
        page = window.content_factory_page
        page.create_campaign()
        source = page.factory.add_source('MANUAL_ARTICLE', 'https://ithutir.com/article', 'Article')
        slot = page.factory.slot(page.slot_id())
        page.factory.edit_slot(slot['id'], source_id=source, board_id=None, content_type='EDUCATIONAL', scheduled_at=slot['scheduled_at'])
        page.open_design()
        pid = page.factory.slot(slot['id'])['pin_id']
        assert window.pin_designer.pin.currentData() == pid
        assert window.pin_designer._canvas_pin_id == pid
        assert window.pages.currentIndex() == MENU.index('PIN')
        assert window.pin_tabs.currentIndex() == 1
        assert window.pin_designer.scene.width() == 1000
        assert window.pin_designer.scene.height() == 1500
        for name in ('CONTENT FACTORY', 'CALENDAR', 'PUBLISHING', 'ANALYTICS', 'TIME', 'BOARD', 'PIN'):
            window.open_page(name)
            assert window.pages.currentIndex() == MENU.index(name)
        empty = Storage(tmp_path / 'empty.sqlite3')
        folder = create_project(empty.conn, tmp_path / 'project')
        empty.close()
        with patch.object(window.pin_designer, 'confirm_discard', return_value=True):
            assert window._switch_project(folder)
        assert page.factory.storage is window.storage
        assert page.campaign.count() == 0
    finally:
        with patch.object(window.pin_designer, 'confirm_discard', return_value=True):
            window.close()
        app.removeEventFilter(theme)
