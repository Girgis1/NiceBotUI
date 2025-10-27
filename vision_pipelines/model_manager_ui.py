"""
Model Manager UI for downloading and managing YOLO models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QMessageBox,
)


class ModelDownloadWorker(QThread):
    """Background thread for downloading YOLO models"""
    
    progress = Signal(str)  # Status message
    finished = Signal(bool, str)  # Success, message
    
    def __init__(self, version: str, size: str):
        super().__init__()
        self.version = version
        self.size = size
    
    def run(self):
        try:
            from .beauty_detector import BeautyProductDetector
            
            self.progress.emit(f"Downloading YOLOv{self.version} {self.size}...")
            success = BeautyProductDetector.download_model(self.version, self.size)
            
            if success:
                self.finished.emit(True, f"Successfully downloaded YOLOv{self.version} {self.size}")
            else:
                self.finished.emit(False, "Download failed")
                
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class ModelManagerDialog(QDialog):
    """Dialog for managing YOLO models"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vision Model Manager")
        self.resize(900, 600)
        self.setModal(True)
        
        self.download_worker: Optional[ModelDownloadWorker] = None
        
        self._init_ui()
        self._load_models()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Title
        title = QLabel("🤖 YOLO Model Manager")
        title.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: #ffffff;
                padding: 10px;
            }
        """)
        layout.addWidget(title)
        
        # Info
        info = QLabel(
            "Manage YOLOv11 and YOLOv8 instance segmentation models for beauty product detection.\n"
            "First download will take 10-100 MB depending on model size."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #e0e0e0; font-size: 13px; padding: 5px;")
        layout.addWidget(info)
        
        # Models table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Model", "Version", "Size", "Status", "Speed", "Action"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #3a3a3a;
                color: #ffffff;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; padding: 6px;")
        layout.addWidget(self.status_label)
        
        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumWidth(120)
        refresh_btn.clicked.connect(self._load_models)
        button_row.addWidget(refresh_btn)
        
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(120)
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        
        layout.addLayout(button_row)
    
    def _load_models(self):
        """Load and display available models"""
        try:
            from .beauty_detector import BeautyProductDetector
            from .fastsam_detector import FastSAMDetector
            
            # Get both YOLO and FastSAM models
            yolo_models = BeautyProductDetector.list_available_models()
            fastsam_models = FastSAMDetector.list_available_models()
            models = yolo_models + fastsam_models
            
            self.table.setRowCount(len(models))
            
            for row, model in enumerate(models):
                # Model name
                name_item = QTableWidgetItem(model['name'])
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 0, name_item)
                
                # Version
                version_item = QTableWidgetItem(f"v{model['version']}")
                version_item.setFlags(version_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 1, version_item)
                
                # Size
                size_item = QTableWidgetItem(model['size'].title())
                size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 2, size_item)
                
                # Status
                status = "✅ Downloaded" if model['exists'] else "⬇️ Not Downloaded"
                status_item = QTableWidgetItem(status)
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                if model['exists']:
                    status_item.setForeground(Qt.green)
                else:
                    status_item.setForeground(Qt.yellow)
                self.table.setItem(row, 3, status_item)
                
                # Speed estimate
                speed_map = {
                    'nano': '🚀 ~30 FPS (fastest)',
                    'small': '⚡ ~20 FPS (balanced)',
                    'medium': '🎯 ~10 FPS (accurate)',
                    'large': '🎓 ~5 FPS (very accurate)',
                    'extra': '💎 ~2 FPS (maximum)',
                }
                speed_item = QTableWidgetItem(speed_map.get(model['size'], 'Unknown'))
                speed_item.setFlags(speed_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 4, speed_item)
                
                # Action button
                if not model['exists']:
                    download_btn = QPushButton("Download")
                    download_btn.clicked.connect(
                        lambda checked=False, v=model['version'], s=model['size']: 
                        self._download_model(v, s)
                    )
                    self.table.setCellWidget(row, 5, download_btn)
                else:
                    status_label = QLabel("✓ Ready")
                    status_label.setAlignment(Qt.AlignCenter)
                    status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
                    self.table.setCellWidget(row, 5, status_label)
            
            self.status_label.setText(f"Found {len(models)} available models")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; padding: 6px;")
            
        except Exception as e:
            self.status_label.setText(f"Error loading models: {e}")
            self.status_label.setStyleSheet("color: #f44336; font-size: 13px; padding: 6px;")
    
    def _download_model(self, version: str, size: str):
        """Start model download in background thread"""
        if self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(
                self,
                "Download in Progress",
                "Please wait for the current download to complete."
            )
            return
        
        # Confirm download
        reply = QMessageBox.question(
            self,
            "Download Model",
            f"Download YOLOv{version} {size}?\n\n"
            f"This will download ~10-100 MB from Ultralytics.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Start download
        self.progress_bar.show()
        self.status_label.setText(f"Downloading YOLOv{version} {size}...")
        self.status_label.setStyleSheet("color: #2196F3; font-size: 13px; padding: 6px;")
        
        self.download_worker = ModelDownloadWorker(version, size)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.start()
    
    def _on_download_progress(self, message: str):
        """Update progress message"""
        self.status_label.setText(message)
    
    def _on_download_finished(self, success: bool, message: str):
        """Handle download completion"""
        self.progress_bar.hide()
        self.status_label.setText(message)
        
        if success:
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; padding: 6px;")
            QMessageBox.information(self, "Download Complete", message)
            self._load_models()  # Refresh table
        else:
            self.status_label.setStyleSheet("color: #f44336; font-size: 13px; padding: 6px;")
            QMessageBox.warning(self, "Download Failed", message)
        
        self.download_worker = None
    
    def closeEvent(self, event):
        """Prevent closing during download"""
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Download in Progress",
                "A download is in progress. Cancel it and close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.download_worker.terminate()
                self.download_worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


__all__ = ["ModelManagerDialog"]

