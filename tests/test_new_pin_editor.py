"""Regression tests for creating a blank pin from the actual editor."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from unittest.mock import patch
import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox
from pinterest_os.designer import PinDesigner
from pinterest_os.storage import Storage

@pytest.fixture
def editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    db = Storage(tmp_path / "editor.sqlite3")
    board = db.create("boards", name="Old board")
    product = db.create("products", name="Old product")
    old = db.create("pins", title="Old pin", description="Old description",
                    tags="old", destination_url="https://example.com/old",
                    board_id=board, product_id=product, status="READY")
    widget = PinDesigner(db)
    widget.pin_directory = lambda: tmp_path
    with patch.object(QMessageBox, "information"):
        widget.save_pin_simple()
    try:
        yield app, db, widget, old
    finally:
        widget.close()
        db.close()

def test_new_pin_is_blank_and_saves_as_separate_record(editor):
    app, db, widget, old = editor
    before = db.get("pins", old)
    before_design = db.get_pin_design(old)
    widget.canva_id.setText("old-canva")
    widget.new_pin_button.click()
    assert widget.pin.currentIndex() == -1
    assert widget.pin.currentData() is None
    assert widget._canvas_pin_id is None
    assert widget.project()["layers"] == []
    assert widget.layers_list.count() == 0
    assert all(not field.text() for field in (
        widget.pin_title, widget.pin_description, widget.pin_tags,
        widget.destination_url, widget.export_pin_id, widget.canva_id, widget.text))
    assert widget.pin_board.currentData() is None
    assert widget.pin_product.currentData() is None
    assert widget.pin_status.currentText() == "DRAFT"
    assert len(db.all("pins")) == 1
    widget.pin_title.setText("New pin")
    widget.pin_description.setText("New description")
    widget.pin_tags.setText("new")
    widget.destination_url.setText("https://example.com/new")
    widget.add_text()
    widget.reload_pins()
    assert widget.pin.currentData() is None
    assert widget.pin_title.text() == "New pin"
    with patch.object(QMessageBox, "information"):
        widget.save_button.click()
    new = widget.pin.currentData()
    assert new != old and new is not None
    assert db.get("pins", new)["title"] == "New pin"
    assert db.get("pins", new)["status"] == "DRAFT"
    assert db.get_pin_design(new)
    assert db.get("pins", old) == before
    assert db.get_pin_design(old) == before_design

def test_new_pin_cancel_preserves_unsaved_metadata(editor):
    app, db, widget, old = editor
    widget.pin_title.setText("Unsaved title")
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as ask:
        widget.new_pin_button.click()
    ask.assert_called_once()
    assert widget.pin.currentData() == old
    assert widget.pin_title.text() == "Unsaved title"
    assert db.get("pins", old)["title"] == "Old pin"
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        widget.new_pin_button.click()
    assert widget.pin_title.text() == ""
    assert db.get("pins", old)["title"] == "Old pin"

def test_invalid_new_pin_does_not_create_record(editor):
    app, db, widget, old = editor
    widget.new_pin_button.click()
    widget.pin_title.setText("Invalid")
    widget.destination_url.setText("not a url")
    with patch.object(QMessageBox, "warning") as warning:
        widget.save_button.click()
    warning.assert_called_once()
    assert len(db.all("pins")) == 1
    assert widget.pin.currentData() is None

def test_new_draft_canvas_cannot_overwrite_selected_saved_pin(editor):
    app, db, widget, old = editor
    widget.new_pin_button.click()
    widget.pin_title.setText("New draft")
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        widget.pin.setCurrentIndex(widget.pin.findData(old))
    assert widget.pin.currentData() is None
    assert widget.pin_title.text() == "New draft"
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        widget.pin.setCurrentIndex(widget.pin.findData(old))
    with patch.object(QMessageBox, "warning") as warning:
        widget.save_button.click()
    warning.assert_called_once()
    assert db.get("pins", old)["title"] == "Old pin"
