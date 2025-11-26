"""TrainTab mirrors Dashboard UI with custom controls and slide-out pane."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QPushButton,
    QFrame,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QComboBox,
    QCheckBox,
    QMessageBox,
)

from tabs.dashboard_tab import DashboardTab
from utils.act_dataset import (
    ActDatasetMeta,
    ensure_dataset,
    list_datasets,
    update_completed_episodes,
)
from utils.act_record_worker import ActRecordWorker


class TrainTab(DashboardTab):
    """Train tab reusing the dashboard UI with custom control labels/layout."""

    def __init__(self, config: dict, parent, device_manager):
        super().__init__(config, parent, device_manager)
        self._customize_header()
        self._customize_controls()
        self._build_side_panel()
        self._init_train_tab_ui()
        # Replace Dashboard's RUN selector contents with ACT datasets only
        self.refresh_run_selector()

    # ------------------------------------------------------------------
    # UI customizations

    def _customize_header(self) -> None:
        if hasattr(self, "run_label"):
            self.run_label.setText("MODEL:")

    def _customize_controls(self) -> None:
        # Internal ACT state
        self._act_worker: ActRecordWorker | None = None
        self._recording_active: bool = False
        self._pending_restart: bool = False
        self._pending_next: bool = False
        self._current_meta: ActDatasetMeta | None = None
        self._current_dataset_id: str | None = None

        if hasattr(self, "start_stop_btn"):
            self.start_stop_btn.setText("START")
            self._apply_start_style()
        if hasattr(self, "loop_button"):
            self.loop_button.setText("Modify")
            self.loop_button.setCheckable(False)
            self.loop_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #555555;
                    color: #ffffff;
                    border: 2px solid #666666;
                    border-radius: 10px;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 12px;
                }
                QPushButton:hover { background-color: #666666; }
                """
            )
            # Use loop button as Modify/Redo
            self.loop_button.clicked.connect(self._on_loop_button_clicked)
        if hasattr(self, "home_btn"):
            try:
                self.home_btn.clicked.disconnect()
            except TypeError:
                # No previous connections or already disconnected
                pass
            self.home_btn.clicked.connect(self._on_next_episode_clicked)
            self.home_btn.hide()
        if hasattr(self, "speed_slider"):
            self.speed_slider.hide()
        if hasattr(self, "speed_value_label"):
            self.speed_value_label.hide()

    def _init_train_tab_ui(self) -> None:
        """Train-tab specific tweaks to the shared dashboard layout."""
        # Replace generic dashboard welcome text with ACT-specific guidance
        if hasattr(self, "log_text"):
            try:
                self.log_text.clear()
            except Exception:
                pass
            self._append_log_entry(
                "info",
                "Train tab configured for ACT data collection. Use START to record episodes; Modify to adjust dataset options.",
                code="act_train_welcome",
            )

            # Insert a compact dataset/episode summary widget just above the log
            parent_widget = self.log_text.parentWidget()
            if parent_widget and parent_widget.layout():
                layout = parent_widget.layout()
                index = layout.indexOf(self.log_text)

                self.dataset_summary_frame = QFrame()
                self.dataset_summary_frame.setStyleSheet(
                    """
                    QFrame {
                        background-color: #252525;
                        border: 1px solid #404040;
                        border-radius: 4px;
                    }
                    """
                )
                frame_layout = QHBoxLayout(self.dataset_summary_frame)
                frame_layout.setContentsMargins(8, 6, 8, 6)
                frame_layout.setSpacing(10)

                self.dataset_summary_label = QLabel("Dataset: none selected")
                self.dataset_summary_label.setStyleSheet(
                    "color: #e0e0e0; font-size: 12px; font-weight: bold;"
                )
                frame_layout.addWidget(self.dataset_summary_label, stretch=1)

                self.episode_summary_label = QLabel("")
                self.episode_summary_label.setStyleSheet(
                    "color: #a0a0a0; font-size: 11px;"
                )
                frame_layout.addWidget(self.episode_summary_label, stretch=0)

                layout.insertWidget(max(0, index), self.dataset_summary_frame)
                self._refresh_dataset_summary()

    # ------------------------------------------------------------------
    # Side pane

    def _build_side_panel(self) -> None:
        self._side_width = 280
        self.side_panel = QFrame(self)
        # Plain panel; edge handled by resize grabber
        self.side_panel.setStyleSheet(
            "QFrame { background-color: #1f1f1f; }"
        )
        self.side_panel.setGeometry(self.width(), 0, self._side_width, self.height())
        self.side_panel.hide()

        # Opaque overlay
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(0, 0, 0, 140);")
        self.overlay.setGeometry(self.rect())
        self.overlay.hide()
        self.overlay.mousePressEvent = lambda event: self._toggle_side_panel(close_only=True)  # type: ignore

        self.side_toggle_btn = QPushButton("<", self)
        self.side_toggle_btn.setFixedSize(30, 80)
        self.side_toggle_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2f2f2f;
                color: #ffffff;
                border: 1px solid #505050;
                border-top-left-radius: 8px;
                border-bottom-left-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a3a; }
            """
        )
        self.side_toggle_btn.clicked.connect(self._toggle_side_panel)
        self._position_side_controls()

        self._side_anim = None
        self._side_open = False

        # Panel content
        layout = QVBoxLayout(self.side_panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        edge_label = QLabel("Recording Options")
        edge_label.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        layout.addWidget(edge_label)

        # Run/model name
        run_row = QHBoxLayout()
        run_label = QLabel("Run Name")
        run_label.setStyleSheet("color: #c0c0c0; font-size: 14px; font-weight: bold;")
        run_row.addWidget(run_label)
        run_row.addStretch()
        self.run_name_edit = QLineEdit()
        self.run_name_edit.setMinimumHeight(40)
        self.run_name_edit.setStyleSheet(
            """
            QLineEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 14px;
            }
            """
        )
        default_run = datetime.now().strftime("act_run_%Y%m%d_%H%M%S")
        self.run_name_edit.setText(default_run)
        run_row.addWidget(self.run_name_edit)
        layout.addLayout(run_row)

        # Existing dataset selector
        ds_row = QHBoxLayout()
        ds_label = QLabel("Dataset")
        ds_label.setStyleSheet("color: #c0c0c0; font-size: 14px; font-weight: bold;")
        ds_row.addWidget(ds_label)
        ds_row.addStretch()
        self.dataset_combo = QComboBox()
        self.dataset_combo.setMinimumHeight(36)
        self.dataset_combo.setStyleSheet(
            """
            QComboBox {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
            }
            QComboBox QAbstractItemView {
                background-color: #303030;
                color: #ffffff;
                selection-background-color: #4CAF50;
            }
            """
        )
        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_selected)
        ds_row.addWidget(self.dataset_combo)
        layout.addLayout(ds_row)

        # Resume toggle
        self.resume_check = QCheckBox("Resume existing dataset")
        self.resume_check.setChecked(True)
        self.resume_check.setStyleSheet(
            """
            QCheckBox {
                color: #c0c0c0;
                font-size: 13px;
                padding: 4px 0;
            }
            QCheckBox::indicator {
                width: 22px;
                height: 22px;
            }
            """
        )
        layout.addWidget(self.resume_check)

        # Arm selection
        arm_row = QHBoxLayout()
        arm_row.setSpacing(8)
        arm_label = QLabel("Arm Mode")
        arm_label.setStyleSheet("color: #c0c0c0; font-size: 14px; font-weight: bold;")
        arm_row.addWidget(arm_label)
        arm_row.addStretch()
        self.arm_group = QButtonGroup(self)
        self.arm_mode = "bimanual"
        for text, mode in (("Left", "left"), ("Right", "right"), ("Bimanual", "bimanual")):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setMinimumHeight(44)
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #404040;
                    color: #ffffff;
                    border: 1px solid #505050;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 8px 12px;
                }
                QPushButton:checked {
                    background-color: #4CAF50;
                    border-color: #66BB6A;
                }
                """
            )
            btn.clicked.connect(lambda checked, m=mode: checked and self._set_arm_mode(m))
            if mode == self.arm_mode:
                btn.setChecked(True)
            self.arm_group.addButton(btn)
            arm_row.addWidget(btn)
        layout.addLayout(arm_row)

        def build_row(label_text, spin: QSpinBox):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #c0c0c0; font-size: 14px; font-weight: bold;")
            row.addWidget(lbl)
            row.addStretch()

            spin.setMinimumHeight(44)
            spin.setButtonSymbols(QSpinBox.NoButtons)
            spin.setStyleSheet(
                """
                QSpinBox {
                    background-color: #2a2a2a;
                    color: #ffffff;
                    border: 1px solid #505050;
                    border-radius: 6px;
                    padding: 6px;
                    font-size: 18px;
                    min-width: 80px;
                }
                """
            )

            btn_up = QPushButton("▲")
            btn_up.setFixedSize(48, 48)
            btn_up.setStyleSheet(
                """
                QPushButton {
                    background-color: #404040;
                    color: #ffffff;
                    border: 1px solid #505050;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #4d4d4d; }
                """
            )
            btn_up.clicked.connect(lambda: spin.setValue(spin.value() + 1))

            btn_down = QPushButton("▼")
            btn_down.setFixedSize(48, 48)
            btn_down.setStyleSheet(
                """
                QPushButton {
                    background-color: #404040;
                    color: #ffffff;
                    border: 1px solid #505050;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #4d4d4d; }
                """
            )
            btn_down.clicked.connect(lambda: spin.setValue(spin.value() - 1))

            spin_row = QHBoxLayout()
            spin_row.setSpacing(8)
            spin_row.addWidget(spin)
            spin_row.addWidget(btn_up)
            spin_row.addWidget(btn_down)

            row.addLayout(spin_row)
            return row

        self.episodes_spin = QSpinBox()
        self.episodes_spin.setRange(30, 999)
        self.episodes_spin.setValue(30)
        layout.addLayout(build_row("Episodes", self.episodes_spin))

        self.seconds_spin = QSpinBox()
        self.seconds_spin.setRange(5, 600)
        self.seconds_spin.setValue(30)
        layout.addLayout(build_row("Seconds", self.seconds_spin))

        # Notes
        notes_label = QLabel("Notes")
        notes_label.setStyleSheet("color: #c0c0c0; font-size: 14px; font-weight: bold;")
        layout.addWidget(notes_label)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Task description / object, e.g. 'Pick and place blocks'")
        self.notes_edit.setMinimumHeight(70)
        self.notes_edit.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 6px;
                font-size: 13px;
            }
            """
        )
        layout.addWidget(self.notes_edit)

        # Teleop trigger
        teleop_row = QHBoxLayout()
        teleop_row.addStretch()
        self.teleop_btn = QPushButton("Teleop")
        self.teleop_btn.setMinimumHeight(44)
        self.teleop_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2f9ee5;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 16px;
            }
            QPushButton:hover { background-color: #238fce; }
            """
        )
        # Placeholder: wiring to be added
        teleop_row.addWidget(self.teleop_btn)
        layout.addLayout(teleop_row)

        # Training launcher (CLI hint)
        train_row = QHBoxLayout()
        train_row.addStretch()
        self.train_btn = QPushButton("Show Train Command")
        self.train_btn.setMinimumHeight(40)
        self.train_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #555555;
                color: white;
                border: 1px solid #666666;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #666666; }
            """
        )
        self.train_btn.clicked.connect(self._on_train_clicked)
        train_row.addWidget(self.train_btn)
        layout.addLayout(train_row)

        # Initial dataset list
        self._refresh_dataset_list()

        layout.addStretch(1)

        # Resize handle on the pane edge (20px)
        self._resize_handle = QFrame(self.side_panel)
        self._resize_handle.setStyleSheet(
            "QFrame { background-color: #777777; }"
        )
        self._resize_handle.setCursor(Qt.SizeHorCursor)
        # Slim 10px handle that sits just outside the pane
        self._resize_handle.setFixedWidth(10)
        self._resize_handle.mousePressEvent = self._on_handle_press  # type: ignore
        self._resize_handle.mouseMoveEvent = self._on_handle_move  # type: ignore
        self._resize_handle.mouseReleaseEvent = self._on_handle_release  # type: ignore
        self._resize_start_x = None
        self._resize_start_width = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_side_controls()
        if self._side_open:
            self.side_panel.setGeometry(
                self.width() - self._side_width, 0, self._side_width, self.height()
            )
        else:
            self.side_panel.setGeometry(self.width(), 0, self._side_width, self.height())
        self.overlay.setGeometry(self.rect())
        self._position_handle()

    def mousePressEvent(self, event):
        if self._side_open:
            if not self.side_panel.geometry().contains(event.pos()) and not self.side_toggle_btn.geometry().contains(
                event.pos()
            ):
                self._toggle_side_panel(close_only=True)
        super().mousePressEvent(event)

    def _position_side_controls(self):
        btn_x = self.width() - self.side_toggle_btn.width()
        btn_y = int(self.height() / 2 - self.side_toggle_btn.height() / 2)
        self.side_toggle_btn.move(btn_x, max(0, btn_y))
        self._position_handle()

    def _toggle_side_panel(self, close_only: bool = False):
        target_open = False if close_only else not self._side_open
        start_x = self.side_panel.x()
        end_x = self.width() - self._side_width if target_open else self.width()

        self.overlay.setVisible(target_open)
        self.overlay.raise_()  # cover everything behind
        self.side_panel.raise_()  # pane above overlay
        self.side_toggle_btn.setVisible(not target_open)
        self._position_handle()

        self.side_panel.show()
        anim = QPropertyAnimation(self.side_panel, b"geometry")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(QRect(start_x, 0, self._side_width, self.height()))
        anim.setEndValue(QRect(end_x, 0, self._side_width, self.height()))
        anim.finished.connect(lambda: self._on_side_anim_finished(target_open))
        anim.start()
        self._side_anim = anim

    def _on_side_anim_finished(self, open_state: bool):
        self._side_open = open_state
        if not open_state:
            self.side_panel.hide()
            self.overlay.hide()
            self.side_toggle_btn.show()

    def _position_handle(self):
        if hasattr(self, "_resize_handle"):
            width = self._resize_handle.width()
            # Place the 10px handle just OUTSIDE the pane on its left edge
            # so it sits between the pop-out panel and the dark background
            # without overlapping any panel content.
            self._resize_handle.setGeometry(-width, 0, width, self.side_panel.height())
            self._resize_handle.raise_()

    def _set_arm_mode(self, mode: str):
        self.arm_mode = mode
        # Update toggle selection when changed programmatically
        if hasattr(self, "arm_group"):
            for btn in self.arm_group.buttons():
                btn.setChecked(btn.text().lower().startswith(mode[0]))

    # ------------------------------------------------------------------
    # Resize handle events
    def _on_handle_press(self, event):
        self._resize_start_x = event.globalX()
        self._resize_start_width = self._side_width

    def _on_handle_move(self, event):
        if self._resize_start_x is None or self._resize_start_width is None:
            return
        delta = self._resize_start_x - event.globalX()
        new_width = max(200, min(600, self._resize_start_width + delta))
        self._side_width = new_width
        self.side_panel.setGeometry(self.width() - self._side_width, 0, self._side_width, self.height())
        self._position_handle()

    def _on_handle_release(self, event):
        self._resize_start_x = None
        self._resize_start_width = None

    # ------------------------------------------------------------------
    # Execution controls: ACT recording instead of dashboard runs
    def toggle_start_stop(self):
        if self._recording_active:
            self._stop_recording()
        else:
            self._start_recording()

    def start_run(self):
        self._start_recording()

    def stop_run(self, quiet: bool = False):
        self._stop_recording()

    # ------------------------------------------------------------------
    # Helpers

    def _apply_start_style(self):
        self.start_stop_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 32px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #388E3C; }
            """
        )

    def _apply_stop_style(self):
        self.start_stop_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #c62828;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 32px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #b71c1c; }
            """
        )

    def _apply_running_ui(self):
        self.start_stop_btn.blockSignals(True)
        self.start_stop_btn.setChecked(True)
        self.start_stop_btn.setText("STOP")
        self._apply_stop_style()
        self.start_stop_btn.blockSignals(False)

        if hasattr(self, "loop_button"):
            self.loop_button.setText("⏮ Redo")
            self.loop_button.show()
            self.loop_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #FFB300;
                    color: #ffffff;
                    border: none;
                    border-radius: 10px;
                    font-size: 24px;
                    font-weight: bold;
                    padding: 12px 16px;
                }
                QPushButton:hover { background-color: #FFA000; }
                """
            )
        if hasattr(self, "home_btn"):
            self.home_btn.setText("⏭ Next")
            self.home_btn.show()
            self.home_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #1976D2;
                    color: white;
                    border: none;
                    border-radius: 10px;
                    font-size: 28px;
                    font-weight: bold;
                    padding: 12px 16px;
                }
                QPushButton:hover { background-color: #1565C0; }
                """
            )

    def _apply_idle_ui(self):
        self.start_stop_btn.blockSignals(True)
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("START")
        self._apply_start_style()
        self.start_stop_btn.blockSignals(False)

        if hasattr(self, "loop_button"):
            self.loop_button.setText("Modify")
            self.loop_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #555555;
                    color: #ffffff;
                    border: 2px solid #666666;
                    border-radius: 10px;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 12px;
                }
                QPushButton:hover { background-color: #666666; }
                """
            )
        if hasattr(self, "home_btn"):
            self.home_btn.hide()

    # ------------------------------------------------------------------
    # Dataset helpers and worker wiring

    def _refresh_dataset_list(self) -> None:
        """Populate dataset dropdown from metadata files."""
        if not hasattr(self, "dataset_combo"):
            return

        metas = list_datasets()
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        self.dataset_combo.addItem("New dataset…", userData=None)

        for meta in metas:
            status = f"{meta.completed_episodes}/{meta.target_episodes}"
            trained_flag = " ✓" if meta.trained else ""
            label = f"{meta.name} ({status}){trained_flag}"
            self.dataset_combo.addItem(label, userData=meta.dataset_id)

        self.dataset_combo.blockSignals(False)
        self._refresh_dataset_summary()

        # Keep header RUN combo in sync with known datasets
        self.refresh_run_selector()

    def _refresh_dataset_summary(self) -> None:
        """Update the compact dataset/episode summary panel."""
        meta = getattr(self, "_current_meta", None)
        if not hasattr(self, "dataset_summary_label") or not hasattr(self, "episode_summary_label"):
            return

        if not meta:
            self.dataset_summary_label.setText("Dataset: none selected")
            self.episode_summary_label.setText("Episodes: 0/0 — Arm: auto")
            return

        mode = (meta.arm_mode or "bimanual").lower()
        mode_display = {
            "left": "Left",
            "right": "Right",
            "bimanual": "Bimanual",
        }.get(mode, mode.title())

        self.dataset_summary_label.setText(f"Dataset: {meta.name}")
        self.episode_summary_label.setText(
            f"Episodes: {meta.completed_episodes}/{meta.target_episodes} • {meta.episode_time_s}s • Arm: {mode_display}"
        )

    # Override RUN selector to show only ACT datasets (trained/untrained)
    def refresh_run_selector(self) -> None:  # type: ignore[override]
        if not hasattr(self, "run_combo"):
            return

        metas = list_datasets()
        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        placeholder = "-- Select a dataset --"
        self.run_combo.addItem(placeholder, userData=None)

        for meta in metas:
            status = "✓ Trained" if meta.trained else "Untrained"
            label = f"{meta.name} ({status})"
            self.run_combo.addItem(label, userData=meta.dataset_id)

        self.run_combo.blockSignals(False)

    # RUN selection in Train tab = pick ACT dataset (trained/untrained)
    def on_run_selection_changed(self, text):  # type: ignore[override]
        if not hasattr(self, "run_combo"):
            return

        index = self.run_combo.currentIndex()
        dataset_id = self.run_combo.itemData(index)
        if not dataset_id:
            self._current_meta = None
            self._current_dataset_id = None
            self._refresh_dataset_summary()
            return

        meta = ActDatasetMeta.load(str(dataset_id))
        if not meta:
            self._append_log_entry(
                "warning",
                f"Could not load dataset metadata for id '{dataset_id}'.",
                code="act_dataset_load_failed_header",
            )
            return

        self._current_meta = meta
        self._current_dataset_id = meta.dataset_id

        # Sync side panel dropdown to match header selection
        if hasattr(self, "dataset_combo"):
            for i in range(self.dataset_combo.count()):
                if self.dataset_combo.itemData(i) == meta.dataset_id:
                    self.dataset_combo.blockSignals(True)
                    self.dataset_combo.setCurrentIndex(i)
                    self.dataset_combo.blockSignals(False)
                    break

        # Apply dataset fields into side panel controls
        if hasattr(self, "run_name_edit"):
            self.run_name_edit.setText(meta.name)
        if hasattr(self, "episodes_spin"):
            self.episodes_spin.setValue(meta.target_episodes)
        if hasattr(self, "seconds_spin"):
            self.seconds_spin.setValue(meta.episode_time_s)
        if hasattr(self, "resume_check"):
            self.resume_check.setChecked(meta.resume)
        if hasattr(self, "notes_edit"):
            self.notes_edit.setPlainText(meta.notes or "")

        self.arm_mode = meta.arm_mode or "bimanual"
        if hasattr(self, "arm_group"):
            for btn in self.arm_group.buttons():
                label = btn.text().lower()
                if self.arm_mode == "left" and "left" in label:
                    btn.setChecked(True)
                elif self.arm_mode == "right" and "right" in label:
                    btn.setChecked(True)
                elif self.arm_mode == "bimanual" and "bimanual" in label:
                    btn.setChecked(True)

        self._refresh_dataset_summary()
        self.action_label.setText(
            f"Dataset “{meta.name}” — {meta.completed_episodes}/{meta.target_episodes} episodes"
        )

    def _on_dataset_selected(self, index: int) -> None:
        data = self.dataset_combo.itemData(index)
        if not data:
            # New dataset; keep current run_name but clear association
            self._current_meta = None
            self._current_dataset_id = None
            return

        meta = ActDatasetMeta.load(str(data))
        if not meta:
            self._append_log_entry(
                "warning",
                f"Could not load dataset metadata for id '{data}'.",
                code="act_dataset_load_failed",
            )
            return

        self._current_meta = meta
        self._current_dataset_id = meta.dataset_id

        # Apply settings to panel
        self.run_name_edit.setText(meta.name)
        self.episodes_spin.setValue(meta.target_episodes)
        self.seconds_spin.setValue(meta.episode_time_s)
        self.resume_check.setChecked(meta.resume)
        self.notes_edit.setPlainText(meta.notes or "")
        self.arm_mode = meta.arm_mode or "bimanual"

        # Update arm button selection
        if hasattr(self, "arm_group"):
            for btn in self.arm_group.buttons():
                mode = btn.text().lower()
                if meta.arm_mode == "left" and "left" in mode:
                    btn.setChecked(True)
                elif meta.arm_mode == "right" and "right" in mode:
                    btn.setChecked(True)
                elif meta.arm_mode == "bimanual" and "bimanual" in mode:
                    btn.setChecked(True)

        # Surface summary
        self._refresh_dataset_summary()
        self.action_label.setText(
            f"Dataset “{meta.name}” — {meta.completed_episodes}/{meta.target_episodes} episodes"
        )

    # UI button handlers

    def _on_loop_button_clicked(self) -> None:
        """Modify when idle, Redo when recording."""
        if self._recording_active:
            # Redo current episode: stop and schedule restart
            self._pending_restart = True
            self._pending_next = False
            self._stop_recording()
        else:
            # Idle: open side panel for settings
            self._toggle_side_panel()

    def _on_next_episode_clicked(self) -> None:
        """Advance to next episode when recording."""
        if not self._recording_active:
            return
        self._pending_next = True
        self._pending_restart = False
        self._stop_recording()

    def _on_train_clicked(self) -> None:
        """Show a lerobot-train command for the current dataset in the log."""
        meta = self._current_meta
        if not meta:
            # Try to materialise metadata from current panel without recording yet
            run_name = self.run_name_edit.text().strip() if hasattr(self, "run_name_edit") else ""
            if not run_name:
                self._append_log_entry(
                    "warning",
                    "Set a Run Name and save at least one episode before training.",
                    code="act_train_no_dataset",
                )
                return

            target_episodes = int(self.episodes_spin.value()) if hasattr(self, "episodes_spin") else 30
            episode_time = int(self.seconds_spin.value()) if hasattr(self, "seconds_spin") else 30
            arm_mode = getattr(self, "arm_mode", "bimanual")
            resume = self.resume_check.isChecked() if hasattr(self, "resume_check") else True
            notes = self.notes_edit.toPlainText().strip() if hasattr(self, "notes_edit") else ""

            meta = ensure_dataset(
                run_name=run_name,
                target_episodes=target_episodes,
                episode_time_s=episode_time,
                arm_mode=arm_mode,
                resume=resume,
                notes=notes,
                existing_id=self._current_dataset_id,
            )
            self._current_meta = meta
            self._current_dataset_id = meta.dataset_id
            self._refresh_dataset_list()

        if meta.completed_episodes <= 0:
            self._append_log_entry(
                "warning",
                f"Dataset “{meta.name}” has no episodes yet. Record some episodes before training.",
                code="act_train_empty",
            )
            return

        output_dir = f"outputs/train/act_{meta.dataset_id}"
        cmd_lines = [
            "lerobot-train \\",
            f"  --dataset.repo_id={meta.repo_id} \\",
            "  --policy.type=act \\",
            f"  --output_dir={output_dir} \\",
            f"  --job_name=act_{meta.dataset_id} \\",
            "  --policy.device=cuda",
        ]
        message = (
            "Training runs on your GPU machine (not on the Jetson).\n"
            "Run this command from your lerobot environment:\n"
            + "\n".join(cmd_lines)
        )
        self._append_log_entry("info", message, code="act_train_command")

    # Core start/stop logic

    def _start_recording(self) -> None:
        if self._recording_active or (self._act_worker and self._act_worker.isRunning()):
            self._append_log_entry(
                "warning",
                "Recording already in progress. Stop before starting another episode.",
                code="act_already_running",
            )
            return

        run_name = self.run_name_edit.text().strip() if hasattr(self, "run_name_edit") else ""
        if not run_name:
            run_name = datetime.now().strftime("act_run_%Y%m%d_%H%M%S")
            self.run_name_edit.setText(run_name)

        target_episodes = int(self.episodes_spin.value()) if hasattr(self, "episodes_spin") else 30
        # Soft clamp to at least 1; UI/plan recommends 30 but we won't hard-enforce
        if target_episodes < 1:
            target_episodes = 1
            self.episodes_spin.setValue(target_episodes)

        episode_time = int(self.seconds_spin.value()) if hasattr(self, "seconds_spin") else 30
        if episode_time < 1:
            episode_time = 1
            self.seconds_spin.setValue(episode_time)

        arm_mode = getattr(self, "arm_mode", "bimanual")
        resume = self.resume_check.isChecked() if hasattr(self, "resume_check") else True
        notes = self.notes_edit.toPlainText().strip() if hasattr(self, "notes_edit") else ""

        # Create or update dataset metadata
        meta = ensure_dataset(
            run_name=run_name,
            target_episodes=target_episodes,
            episode_time_s=episode_time,
            arm_mode=arm_mode,
            resume=resume,
            notes=notes,
            existing_id=self._current_dataset_id,
        )
        self._current_meta = meta
        self._current_dataset_id = meta.dataset_id
        self._refresh_dataset_list()
        self._refresh_dataset_summary()

        if meta.completed_episodes >= meta.target_episodes:
            self._append_log_entry(
                "info",
                f"Dataset “{meta.name}” already complete ({meta.completed_episodes}/{meta.target_episodes}).",
                code="act_dataset_complete",
            )
            self._refresh_dataset_summary()
            self._apply_idle_ui()
            return

        episode_index = meta.completed_episodes + 1
        resume_flag = episode_index > 1 and meta.resume

        # Build worker
        self._act_worker = ActRecordWorker(
            self.config,
            repo_id=meta.repo_id,
            single_task=meta.name,
            episode_index=episode_index,
            target_episodes=meta.target_episodes,
            episode_time_s=meta.episode_time_s,
            arm_mode=meta.arm_mode,
            resume=resume_flag,
            display_data=False,
        )
        self._act_worker.status_update.connect(self._on_act_status)
        self._act_worker.log_message.connect(self._on_act_log)
        self._act_worker.episode_progress.connect(self._on_episode_progress)
        self._act_worker.completed.connect(self._on_act_completed)

        self._recording_active = True
        self.is_running = True
        self._pending_restart = False
        self._pending_next = False

        self._apply_running_ui()
        self._set_action_label_style("#4CAF50")
        self.action_label.setText(
            f"Recording ep {episode_index}/{meta.target_episodes} for “{meta.name}”…"
        )
        self._append_log_entry(
            "action",
            f"Starting ACT episode {episode_index}/{meta.target_episodes} for dataset “{meta.name}”.",
            code="act_start_episode",
        )

        from datetime import datetime as _dt

        self.start_time = _dt.now()
        self.elapsed_seconds = 0
        self.timer.start(1000)

        self._act_worker.start()

    def _stop_recording(self) -> None:
        if self._act_worker and self._act_worker.isRunning():
            self._act_worker.request_stop()

        self._recording_active = False
        self.is_running = False
        self.timer.stop()
        self._apply_idle_ui()

    # Worker signal handlers

    def _on_act_status(self, text: str) -> None:
        self.action_label.setText(text)

    def _on_act_log(self, level: str, message: str) -> None:
        self._append_log_entry(level, message, code="act_record")

    def _on_episode_progress(self, current: int, total: int) -> None:
        if not self._current_meta:
            return
        self.action_label.setText(
            f"Recording ep {current}/{total} for “{self._current_meta.name}”…"
        )

    def _on_act_completed(self, success: bool, summary: str) -> None:
        self.timer.stop()
        self._recording_active = False
        self.is_running = False

        meta = self._current_meta
        if success and meta:
            updated = update_completed_episodes(meta.dataset_id, 1)
            if updated:
                self._current_meta = updated
                self._append_log_entry(
                    "success",
                    f"Episode saved ({updated.completed_episodes}/{updated.target_episodes}) for “{updated.name}”.",
                    code="act_episode_saved",
                )
                self._refresh_dataset_summary()
                self.action_label.setText(
                    f"✓ Episode {updated.completed_episodes}/{updated.target_episodes} saved"
                )
            else:
                self._append_log_entry(
                    "warning",
                    "Episode completed but metadata could not be updated.",
                    code="act_meta_update_failed",
                )
        elif not success:
            self._append_log_entry("warning", summary, code="act_episode_failed")

        self._refresh_dataset_list()
        worker = self._act_worker
        self._act_worker = None
        if worker:
            worker.deleteLater()

        # Decide next action: restart same episode, advance to next, or idle
        meta = self._current_meta
        if self._pending_restart and meta and meta.completed_episodes < meta.target_episodes:
            self._pending_restart = False
            self._pending_next = False
            self._start_recording()
            return

        if self._pending_next and meta and meta.completed_episodes < meta.target_episodes:
            self._pending_next = False
            self._pending_restart = False
            self._start_recording()
            return

        # No pending follow-up: reset UI
        self._pending_restart = False
        self._pending_next = False
        self._apply_idle_ui()
