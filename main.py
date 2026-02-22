"""
Main Qt application for album selection and management
"""
import sys
import os
import json
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                             QLineEdit, QLabel, QProgressBar, QMessageBox, QFileDialog,
                             QCheckBox, QListWidget, QListWidgetItem, QGroupBox,
                             QHeaderView, QAbstractItemView, QTextEdit, QSplitter,
                             QScrollArea, QFrame, QMenuBar, QMenu, QGridLayout, QToolButton)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QImage, QShortcut, QKeySequence, QClipboard
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    MULTIMEDIA_AVAILABLE = True
except ImportError:
    MULTIMEDIA_AVAILABLE = False
    print("Warning: PyQt6.QtMultimedia not available. Audio playback will be disabled.")
from PIL import Image
from database import AlbumDatabase
from scanner import AlbumScanner
from mover import AlbumMover


class ScanThread(QThread):
    """Thread for scanning albums"""
    progress = pyqtSignal(int, int)  # files_scanned, albums_found
    finished = pyqtSignal(int)  # total_albums
    
    def __init__(self, scanner, root_path):
        super().__init__()
        self.scanner = scanner
        self.root_path = root_path
    
    def run(self):
        def progress_callback(files, albums):
            self.progress.emit(files, albums)
        
        total = self.scanner.scan_directory(self.root_path, progress_callback)
        self.finished.emit(total)


class MultiScanThread(QThread):
    """Thread for scanning multiple directories"""
    progress = pyqtSignal(int, int)  # files_scanned, albums_found
    finished = pyqtSignal(int)  # total_albums
    
    def __init__(self, scanner, root_paths):
        super().__init__()
        self.scanner = scanner
        self.root_paths = root_paths
    
    def run(self):
        total_albums = 0
        total_files = 0
        
        def progress_callback(files, albums):
            self.progress.emit(files, albums)
        
        for root_path in self.root_paths:
            try:
                albums_found = self.scanner.scan_directory(root_path, progress_callback)
                total_albums += albums_found
            except Exception as e:
                print(f"Error scanning {root_path}: {e}")
        
        self.finished.emit(total_albums)


class MoveThread(QThread):
    """Thread for moving albums"""
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(int, int, list, int)  # success_count, total, errors, skipped_count
    
    def __init__(self, mover, album_ids, destination):
        super().__init__()
        self.mover = mover
        self.album_ids = album_ids
        self.destination = destination
    
    def run(self):
        def progress_callback(current, total):
            self.progress.emit(current, total)
        
        if len(self.album_ids) == 1:
            success, message = self.mover.move_album(
                self.album_ids[0], self.destination, progress_callback
            )
            if success:
                self.finished.emit(1, 1, [], 0)
            else:
                # Check if it was skipped (already exists)
                skipped = 1 if "already exists" in message.lower() or "skipped" in message.lower() else 0
                self.finished.emit(0, 1, [message], skipped)
        else:
            success_count, total, errors, skipped_count = self.mover.move_favorites(
                self.destination, progress_callback
            )
            self.finished.emit(success_count, total, errors, skipped_count)


class AlbumSelectionApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = AlbumDatabase()
        self.scanner = AlbumScanner(self.db)
        self.mover = AlbumMover(self.db)
        self.scan_thread = None
        self.move_thread = None
        
        self.init_ui()
        self.setup_shortcuts()
        self.load_exclude_words()
        self.load_source_directories()
        # Refresh albums after UI is fully initialized
        self.refresh_albums()
    
    def init_ui(self):
        self.setWindowTitle("Local Music Collection Curator")
        self.setGeometry(100, 100, 1400, 900)
        
        # Create menu bar
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        export_action = file_menu.addAction("💾 Export Favorites...")
        export_action.triggered.connect(self.export_favorites)
        import_action = file_menu.addAction("📥 Import Favorites...")
        import_action.triggered.connect(self.import_favorites)
        file_menu.addSeparator()
        clear_action = file_menu.addAction("🗑️ Clear Database...")
        clear_action.triggered.connect(self.clear_database)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        scan_action = tools_menu.addAction("🔍 Scan Albums")
        scan_action.triggered.connect(self.start_scan)
        refresh_action = tools_menu.addAction("🔄 Refresh")
        refresh_action.triggered.connect(self.refresh_albums)
        
        # Apply modern styling with larger fonts
        self.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 13px;
                font-weight: 500;
                min-height: 32px;
            }
            QPushButton:hover {
                opacity: 0.85;
            }
            QPushButton:pressed {
                opacity: 0.7;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                font-size: 13px;
            }
            QLineEdit {
                padding: 6px;
                border: 2px solid #ccc;
                border-radius: 4px;
                font-size: 12px;
                min-height: 28px;
            }
            QLineEdit:focus {
                border: 2px solid #4CAF50;
            }
            QListWidget {
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 4px;
                min-height: 24px;
            }
            QTableWidget {
                border: 2px solid #ddd;
                border-radius: 4px;
                gridline-color: #eee;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QLabel {
                font-size: 12px;
            }
            QCheckBox {
                font-size: 12px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Top section - Controls (compact layout)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        
        # Source directories (compact)
        source_group = QGroupBox("Source Directories")
        source_group.setMaximumHeight(120)
        source_layout = QVBoxLayout()
        source_layout.setContentsMargins(8, 8, 8, 8)
        source_layout.setSpacing(4)
        
        # Source directories list (compact)
        self.source_list = QListWidget()
        self.source_list.setMaximumHeight(50)
        source_input_layout = QHBoxLayout()
        source_input_layout.setSpacing(4)
        self.source_path_input = QLineEdit()
        self.source_path_input.setPlaceholderText("Enter or browse directory path...")
        self.source_path_input.setMaximumWidth(400)
        source_add_btn = QPushButton("➕ Add")
        source_add_btn.setMinimumWidth(80)
        source_add_btn.setMinimumHeight(32)
        source_add_btn.setToolTip("Add directory")
        source_add_btn.clicked.connect(self.add_source_directory)
        source_browse_btn = QPushButton("📁 Browse")
        source_browse_btn.setMinimumWidth(90)
        source_browse_btn.setMinimumHeight(32)
        source_browse_btn.setToolTip("Browse for directory")
        source_browse_btn.clicked.connect(self.browse_source)
        source_remove_btn = QPushButton("➖ Remove")
        source_remove_btn.setMinimumWidth(90)
        source_remove_btn.setMinimumHeight(32)
        source_remove_btn.setToolTip("Remove selected directory")
        source_remove_btn.clicked.connect(self.remove_source_directory)
        
        # Scan and Refresh buttons
        self.scan_btn = QPushButton("🔍 Scan")
        self.scan_btn.setMinimumWidth(100)
        self.scan_btn.setMinimumHeight(32)
        self.scan_btn.clicked.connect(self.start_scan)
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setMinimumWidth(100)
        refresh_btn.setMinimumHeight(32)
        refresh_btn.setToolTip("Refresh album list")
        refresh_btn.clicked.connect(self.refresh_albums)
        
        source_input_layout.addWidget(self.source_path_input)
        source_input_layout.addWidget(source_add_btn)
        source_input_layout.addWidget(source_browse_btn)
        source_input_layout.addWidget(source_remove_btn)
        source_input_layout.addWidget(self.scan_btn)
        source_input_layout.addWidget(refresh_btn)
        source_input_layout.addStretch()
        
        source_layout.addWidget(self.source_list)
        source_layout.addLayout(source_input_layout)
        source_group.setLayout(source_layout)
        
        # Load saved source directories
        self.load_source_directories()
        
        controls_layout.addWidget(source_group)
        main_layout.addLayout(controls_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # Middle section - Filters and Exclude Words (compact)
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        
        # Exclude words section (compact)
        exclude_group = QGroupBox("Exclude Words")
        exclude_group.setMaximumHeight(140)
        exclude_layout = QVBoxLayout()
        exclude_layout.setContentsMargins(8, 8, 8, 8)
        exclude_layout.setSpacing(4)
        
        exclude_input_layout = QHBoxLayout()
        exclude_input_layout.setSpacing(4)
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText("Enter word to exclude...")
        add_exclude_btn = QPushButton("➕ Add")
        add_exclude_btn.setMinimumWidth(80)
        add_exclude_btn.setMinimumHeight(32)
        add_exclude_btn.setToolTip("Add exclude word")
        add_exclude_btn.clicked.connect(self.add_exclude_word)
        remove_exclude_btn = QPushButton("➖ Remove")
        remove_exclude_btn.setMinimumWidth(90)
        remove_exclude_btn.setMinimumHeight(32)
        remove_exclude_btn.setToolTip("Remove selected word")
        remove_exclude_btn.clicked.connect(self.remove_exclude_word)
        
        exclude_input_layout.addWidget(self.exclude_input)
        exclude_input_layout.addWidget(add_exclude_btn)
        exclude_input_layout.addWidget(remove_exclude_btn)
        
        self.exclude_list = QListWidget()
        self.exclude_list.setMaximumHeight(70)
        
        exclude_layout.addWidget(self.exclude_list)
        exclude_layout.addLayout(exclude_input_layout)
        exclude_group.setLayout(exclude_layout)
        
        # Filter options (compact)
        filter_group = QGroupBox("Filters")
        filter_group.setMaximumHeight(140)
        filter_layout_group = QVBoxLayout()
        filter_layout_group.setContentsMargins(8, 8, 8, 8)
        filter_layout_group.setSpacing(6)
        self.favorite_only_check = QCheckBox("⭐ Show Favorites Only")
        self.favorite_only_check.stateChanged.connect(self.refresh_albums)
        self.favorites_count_label = QLabel("(0 favorites)")
        self.favorites_count_label.setStyleSheet("color: #666; font-size: 11px;")
        filter_layout_group.addWidget(self.favorite_only_check)
        filter_layout_group.addWidget(self.favorites_count_label)
        filter_layout_group.addStretch()
        filter_group.setLayout(filter_layout_group)
        
        filter_layout.addWidget(exclude_group, 2)
        filter_layout.addWidget(filter_group, 1)
        main_layout.addLayout(filter_layout)
        
        # Albums section with splitter (table + detail panel)
        albums_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Albums table (left side)
        albums_table_widget = QWidget()
        albums_table_layout = QVBoxLayout(albums_table_widget)
        albums_table_layout.setContentsMargins(0, 0, 0, 0)
        
        self.albums_table = QTableWidget()
        self.albums_table.setColumnCount(6)
        self.albums_table.setHorizontalHeaderLabels([
            "Favorite", "Album Name", "Artist", "Year", "Files", "Size"
        ])
        self.albums_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.albums_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.albums_table.horizontalHeader().setStretchLastSection(True)
        self.albums_table.setColumnWidth(0, 80)
        self.albums_table.setColumnWidth(1, 300)
        self.albums_table.setColumnWidth(2, 200)
        self.albums_table.setColumnWidth(3, 80)
        self.albums_table.setColumnWidth(4, 80)
        self.albums_table.itemDoubleClicked.connect(self.toggle_favorite_item)
        self.albums_table.itemChanged.connect(self.on_item_changed)
        self.albums_table.itemSelectionChanged.connect(self.on_album_selected)
        self.albums_table.setAlternatingRowColors(True)  # Make rows more visible
        self.albums_table.setShowGrid(True)  # Show grid lines
        self._updating_favorites = False  # Flag to prevent recursive updates
        
        albums_table_layout.addWidget(self.albums_table)
        albums_splitter.addWidget(albums_table_widget)
        
        # Detail panel (right side) - Main container with splitter for metadata sidebar
        detail_panel_container = QWidget()
        detail_panel_main_layout = QHBoxLayout(detail_panel_container)
        detail_panel_main_layout.setContentsMargins(0, 0, 0, 0)
        detail_panel_main_layout.setSpacing(0)
        
        # Left side: Album details
        detail_panel = QGroupBox("Album Details")
        detail_layout = QVBoxLayout()
        
        # Create horizontal splitter for thumbnail and songs list
        thumbnail_songs_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Thumbnail
        thumbnail_container = QWidget()
        thumbnail_layout = QVBoxLayout(thumbnail_container)
        thumbnail_layout.setContentsMargins(0, 0, 0, 0)
        thumbnail_label_header = QLabel("Cover Art:")
        thumbnail_label_header.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setMinimumSize(200, 200)
        self.thumbnail_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        self.thumbnail_label.setText("No album selected")
        self.thumbnail_label.setScaledContents(False)  # We'll scale manually
        self.current_thumbnail_path = None  # Store current thumbnail path
        thumbnail_layout.addWidget(thumbnail_label_header)
        thumbnail_layout.addWidget(self.thumbnail_label)
        thumbnail_layout.addStretch()
        
        # Right side: Songs list
        songs_container = QWidget()
        songs_layout = QVBoxLayout(songs_container)
        songs_layout.setContentsMargins(0, 0, 0, 0)
        songs_label = QLabel("Songs:")
        songs_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.songs_list = QListWidget()
        self.songs_list.setStyleSheet("""
            QListWidget {
                font-size: 12px;
                padding: 0px;
                margin: 0px;
            }
            QListWidget::item {
                padding: 0px;
                margin: 0px;
                border-bottom: 1px solid #e0e0e0;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
            }
        """)
        # Connect song selection to show metadata
        self.songs_list.itemClicked.connect(self.on_song_clicked)
        songs_layout.addWidget(songs_label)
        songs_layout.addWidget(self.songs_list)
        
        # Add to splitter
        thumbnail_songs_splitter.addWidget(thumbnail_container)
        thumbnail_songs_splitter.addWidget(songs_container)
        thumbnail_songs_splitter.setStretchFactor(0, 1)  # Thumbnail
        thumbnail_songs_splitter.setStretchFactor(1, 1)  # Songs list
        thumbnail_songs_splitter.setSizes([300, 300])  # Initial sizes
        
        # Metadata
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setMaximumHeight(150)
        
        # Audio player (if available)
        self.media_player = None
        self.audio_output = None
        self.currently_playing_item = None
        if MULTIMEDIA_AVAILABLE:
            try:
                self.audio_output = QAudioOutput()
                self.media_player = QMediaPlayer()
                self.media_player.setAudioOutput(self.audio_output)
            except Exception as e:
                print(f"Warning: Could not initialize audio player: {e}")
        
        detail_layout.addWidget(thumbnail_songs_splitter)
        detail_layout.addWidget(QLabel("Metadata:"))
        detail_layout.addWidget(self.metadata_text)
        detail_panel.setLayout(detail_layout)
        
        # Add detail panel to main container
        detail_panel_main_layout.addWidget(detail_panel)
        
        # Right side: File Metadata Sidebar (initially hidden)
        self.file_metadata_sidebar = QGroupBox("File Metadata")
        self.file_metadata_sidebar.setMinimumWidth(300)
        self.file_metadata_sidebar.setMaximumWidth(400)
        self.file_metadata_sidebar.setVisible(False)
        self.file_metadata_sidebar.setStyleSheet("""
            QGroupBox {
                background-color: #f9f9f9;
                border-left: 3px solid #4CAF50;
            }
        """)
        
        file_metadata_layout = QVBoxLayout()
        
        # Close button
        close_btn_layout = QHBoxLayout()
        close_btn_layout.addStretch()
        close_metadata_btn = QPushButton("✕ Close")
        close_metadata_btn.setMaximumWidth(80)
        close_metadata_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        close_metadata_btn.clicked.connect(self.hide_file_metadata_sidebar)
        close_btn_layout.addWidget(close_metadata_btn)
        file_metadata_layout.addLayout(close_btn_layout)
        
        # Metadata content (scrollable)
        self.file_metadata_content = QTextEdit()
        self.file_metadata_content.setReadOnly(True)
        self.file_metadata_content.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        file_metadata_layout.addWidget(self.file_metadata_content)
        
        self.file_metadata_sidebar.setLayout(file_metadata_layout)
        detail_panel_main_layout.addWidget(self.file_metadata_sidebar)
        
        albums_splitter.addWidget(detail_panel_container)
        albums_splitter.setStretchFactor(0, 2)  # Table takes 2/3
        albums_splitter.setStretchFactor(1, 1)  # Detail takes 1/3
        
        main_layout.addWidget(albums_splitter)
        
        # Bottom section - Actions (2 rows, compact)
        actions_container = QWidget()
        actions_layout = QVBoxLayout(actions_container)
        actions_layout.setSpacing(6)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        
        # Row 1: Destination with Copy Options
        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)
        dest_label = QLabel("Destination:")
        dest_label.setMinimumWidth(90)
        dest_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.dest_path = QLineEdit()
        self.dest_path.setPlaceholderText("Select destination (pendrive/mounted location)...")
        dest_browse_btn = QPushButton("📁 Browse")
        dest_browse_btn.setMinimumWidth(100)
        dest_browse_btn.setMinimumHeight(32)
        dest_browse_btn.setToolTip("Browse destination")
        dest_browse_btn.clicked.connect(self.browse_destination)
        
        # Create dropdown button for copy operations
        self.copy_menu_btn = QToolButton()
        self.copy_menu_btn.setText("📋 Copy Options ▼")
        self.copy_menu_btn.setMinimumWidth(200)
        self.copy_menu_btn.setMinimumHeight(32)
        self.copy_menu_btn.setStyleSheet("""
            QToolButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
                text-align: left;
                padding-left: 12px;
            }
            QToolButton:hover {
                background-color: #45a049;
            }
            QToolButton::menu-indicator {
                image: none;
                width: 0px;
            }
        """)
        self.copy_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        
        # Create menu
        copy_menu = QMenu(self.copy_menu_btn)
        copy_menu.setStyleSheet("""
            QMenu {
                font-size: 13px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px;
                min-width: 200px;
            }
            QMenu::item:selected {
                background-color: #e3f2fd;
            }
            QMenu::separator {
                height: 1px;
                background-color: #ddd;
                margin: 4px 0px;
            }
        """)
        
        # Copy to location section
        copy_menu.addSection("📁 Copy to Location")
        copy_selected_action = copy_menu.addAction("📋 Copy Selected Albums")
        copy_selected_action.triggered.connect(self.move_selected)
        
        copy_favorites_action = copy_menu.addAction("⭐ Copy Favorite Albums")
        copy_favorites_action.triggered.connect(self.move_favorites)
        
        copy_all_favorites_action = copy_menu.addAction("💚 Copy All Favorites")
        copy_all_favorites_action.triggered.connect(self.copy_favorites_to_location)
        
        copy_menu.addSeparator()
        
        # Copy to clipboard section
        copy_menu.addSection("📄 Copy Paths to Clipboard")
        copy_selected_paths_action = copy_menu.addAction("📄 Copy Selected Paths")
        copy_selected_paths_action.triggered.connect(self.copy_selected_to_clipboard)
        
        copy_fav_paths_action = copy_menu.addAction("📄 Copy Favorite Paths")
        copy_fav_paths_action.triggered.connect(self.copy_favorites_to_clipboard)
        
        self.copy_menu_btn.setMenu(copy_menu)
        
        dest_row.addWidget(dest_label)
        dest_row.addWidget(self.dest_path)
        dest_row.addWidget(dest_browse_btn)
        dest_row.addWidget(self.copy_menu_btn)
        dest_row.addStretch()
        
        actions_layout.addLayout(dest_row)
        
        main_layout.addWidget(actions_container)
    
    def browse_source(self):
        path = QFileDialog.getExistingDirectory(self, "Select Source Directory")
        if path:
            self.source_path_input.setText(path)
    
    def add_source_directory(self):
        """Add a source directory to the list"""
        path = self.source_path_input.text().strip()
        if path and os.path.exists(path):
            if self.db.add_source_directory(path):
                self.load_source_directories()
                self.source_path_input.clear()
                self.statusBar().showMessage(f"Added source directory: {path}")
            else:
                QMessageBox.warning(self, "Error", "Failed to add source directory (may already exist)")
        else:
            QMessageBox.warning(self, "Invalid Path", "Please enter a valid directory path")
    
    def remove_source_directory(self):
        """Remove selected source directory"""
        current_item = self.source_list.currentItem()
        if current_item:
            path = current_item.text()
            reply = QMessageBox.question(
                self, "Remove Source Directory",
                f"Remove source directory:\n{path}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.db.remove_source_directory(path)
                self.load_source_directories()
                self.statusBar().showMessage(f"Removed source directory: {path}")
        else:
            QMessageBox.warning(self, "No Selection", "Please select a source directory to remove")
    
    def load_source_directories(self):
        """Load and display source directories"""
        self.source_list.clear()
        directories = self.db.get_source_directories()
        for directory in directories:
            self.source_list.addItem(directory)
        
        # If no directories, add default one
        if not directories:
            default_path = "/media/vinay-vengala/Seagate Backup Plus Drive/JioSaavn-Songs"
            if os.path.exists(default_path):
                self.db.add_source_directory(default_path)
                self.load_source_directories()
    
    def browse_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Select Destination Directory")
        if path:
            self.dest_path.setText(path)
    
    def start_scan(self):
        # Get all source directories
        source_directories = self.db.get_source_directories()
        if not source_directories:
            QMessageBox.warning(self, "Error", "Please add at least one source directory")
            return
        
        # Validate all directories exist
        valid_directories = []
        for directory in source_directories:
            if os.path.exists(directory):
                valid_directories.append(directory)
            else:
                QMessageBox.warning(self, "Invalid Directory", 
                                  f"Directory does not exist:\n{directory}\n\nRemoving from list.")
                self.db.remove_source_directory(directory)
        
        if not valid_directories:
            QMessageBox.warning(self, "Error", "No valid source directories found")
            self.load_source_directories()
            return
        
        self.scan_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        
        # Create a thread that scans all directories
        self.scan_thread = MultiScanThread(self.scanner, valid_directories)
        self.scan_thread.progress.connect(self.on_scan_progress)
        self.scan_thread.finished.connect(self.on_scan_finished)
        self.scan_thread.start()
    
    def on_scan_progress(self, files, albums):
        self.statusBar().showMessage(f"Scanning... Files: {files}, Albums: {albums}")
    
    def on_scan_finished(self, total):
        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Scan complete! Found {total} albums")
        
        # Force UI update and process events to ensure database commits are visible
        QApplication.processEvents()
        
        # Small delay to ensure all database transactions are committed
        QTimer.singleShot(100, lambda: self.refresh_albums_after_scan(total))
    
    def refresh_albums_after_scan(self, total):
        """Refresh albums after scan with proper timing"""
        # Force refresh
        self.refresh_albums()
        
        # Verify albums are showing
        albums = self.db.get_all_albums()
        actual_count = len(albums)
        
        # Show message
        if actual_count > 0:
            QMessageBox.information(self, "Scan Complete", 
                                  f"Found {total} albums\n\n"
                                  f"Displaying {actual_count} album(s) in the table.")
        else:
            QMessageBox.warning(self, "Scan Complete", 
                              f"Found {total} albums, but none are visible.\n\n"
                              "This may be due to filtering. Please check your exclude words.")
    
    def refresh_albums(self):
        try:
            # Check if UI is initialized
            if not hasattr(self, 'albums_table') or not hasattr(self, 'favorite_only_check'):
                print("Warning: UI not fully initialized, skipping refresh")
                return
            
            exclude_words = self.get_exclude_words()
            favorite_only = self.favorite_only_check.isChecked()
            
            # Get total albums in database (before any filtering)
            all_albums = self.db.get_all_albums()
            total_found = len(all_albums)
            
            # Get albums after exclude words filter (but before favorite filter)
            albums_after_exclude = self.db.get_all_albums(exclude_words=exclude_words, 
                                                         favorite_only=False)
            excluded_count = total_found - len(albums_after_exclude)
            
            # Get final filtered albums (after both exclude words and favorite filter)
            albums = self.db.get_all_albums(exclude_words=exclude_words, 
                                           favorite_only=favorite_only)
            showing_count = len(albums)
            
            # Update favorites count - count from current filtered list if showing favorites only
            if favorite_only:
                favorites_count = len(albums)
            else:
                # Only query separately if not already showing favorites
                try:
                    all_favorites = self.db.get_all_albums(favorite_only=True)
                    favorites_count = len(all_favorites)
                except Exception as e:
                    print(f"Error getting favorites count: {e}")
                    # If query fails, just count from current list
                    favorites_count = sum(1 for a in albums if a.get('is_favorite'))
            
            if hasattr(self, 'favorites_count_label'):
                self.favorites_count_label.setText(f"({favorites_count} favorites)")
            
            # Temporarily block signals to prevent triggering itemChanged during refresh
            self._updating_favorites = True
            self.albums_table.blockSignals(True)
            
            self.albums_table.setRowCount(len(albums))
            
            for row, album in enumerate(albums):
                # Favorite checkbox
                favorite_item = QTableWidgetItem()
                favorite_item.setCheckState(Qt.CheckState.Checked if album['is_favorite'] 
                                          else Qt.CheckState.Unchecked)
                favorite_item.setData(Qt.ItemDataRole.UserRole, album['id'])
                self.albums_table.setItem(row, 0, favorite_item)
                
                # Album name
                self.albums_table.setItem(row, 1, QTableWidgetItem(album['album_name'] or "Unknown"))
                
                # Artist
                self.albums_table.setItem(row, 2, QTableWidgetItem(album['artist'] or "Unknown"))
                
                # Year
                year_str = str(album['year']) if album['year'] else "N/A"
                self.albums_table.setItem(row, 3, QTableWidgetItem(year_str))
                
                # File count
                self.albums_table.setItem(row, 4, QTableWidgetItem(str(album['file_count'])))
                
                # Size
                size_mb = album['total_size'] / (1024 * 1024)
                size_str = f"{size_mb:.2f} MB"
                self.albums_table.setItem(row, 5, QTableWidgetItem(size_str))
            
            # Re-enable signals after refresh
            self.albums_table.blockSignals(False)
            self._updating_favorites = False
            
            # Update status bar with detailed information
            status_message = f"Found: {total_found}"
            if excluded_count > 0:
                status_message += f" | Excluded: {excluded_count}"
            if favorite_only:
                status_message += f" | Showing: {showing_count} (Favorites only)"
            else:
                status_message += f" | Showing: {showing_count}"
            self.statusBar().showMessage(status_message)
            
            # Force table update and refresh
            self.albums_table.viewport().update()
            self.albums_table.update()
            self.albums_table.resizeColumnsToContents()
            
            # Scroll to top
            if len(albums) > 0:
                self.albums_table.scrollToTop()
            
            # Force UI update to ensure table is visible
            QApplication.processEvents()
            
        except Exception as e:
            print(f"Error in refresh_albums: {e}")
            import traceback
            traceback.print_exc()
            self.statusBar().showMessage(f"Error refreshing albums: {str(e)}")
    
    def clear_database(self):
        """Clear all album data from database"""
        reply = QMessageBox.question(
            self, "Clear Database", 
            "Are you sure you want to clear all album data?\n\n"
            "This will remove all scanned albums, but will keep your exclude words.\n"
            "You will need to scan again to repopulate the database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Clear albums and files, but keep exclude words
                self.db.clear_database()
                
                # Clear thumbnail directory
                import shutil
                thumb_dir = Path("thumbnails")
                if thumb_dir.exists():
                    shutil.rmtree(thumb_dir)
                
                # Refresh UI
                self.refresh_albums()
                self.thumbnail_label.clear()
                self.thumbnail_label.setText("No album selected")
                self.metadata_text.clear()
                
                QMessageBox.information(
                    self, "Database Cleared", 
                    "All album data has been cleared.\n\n"
                    "You can now scan your music collection again."
                )
                self.statusBar().showMessage("Database cleared - ready for new scan")
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", 
                    f"Error clearing database:\n{str(e)}"
                )
    
    def on_album_selected(self):
        """Display album details when an album is selected"""
        selected_rows = self.albums_table.selectionModel().selectedRows()
        if not selected_rows:
            self.thumbnail_label.clear()
            self.thumbnail_label.setText("No album selected")
            self.metadata_text.clear()
            self.songs_list.clear()
            return
        
        # Get first selected album
        row = selected_rows[0].row()
        favorite_item = self.albums_table.item(row, 0)
        album_id = favorite_item.data(Qt.ItemDataRole.UserRole)
        
        # Get album from database
        albums = self.db.get_all_albums()
        album = next((a for a in albums if a['id'] == album_id), None)
        
        if not album:
            return
        
        # Display thumbnail
        thumbnail_path = album.get('thumbnail_path')
        self.current_thumbnail_path = thumbnail_path
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                # Load and display image
                pixmap = QPixmap(thumbnail_path)
                if not pixmap.isNull():
                    # Scale to fit label while maintaining aspect ratio (max 300x300)
                    scaled_pixmap = pixmap.scaled(
                        300, 300,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.thumbnail_label.setPixmap(scaled_pixmap)
                else:
                    self.thumbnail_label.clear()
                    self.thumbnail_label.setText("Invalid image")
            except Exception as e:
                print(f"Error loading thumbnail: {e}")
                self.thumbnail_label.clear()
                self.thumbnail_label.setText("Error loading image")
        else:
            self.thumbnail_label.clear()
            self.thumbnail_label.setText("No cover art available")
        
        # Display metadata
        metadata_html = f"""
        <h3>{album.get('album_name', 'Unknown Album')}</h3>
        <p><b>Artist:</b> {album.get('artist', 'Unknown')}</p>
        <p><b>Year:</b> {album.get('year', 'N/A')}</p>
        <p><b>Genre:</b> {album.get('genre', 'N/A')}</p>
        <p><b>Files:</b> {album.get('file_count', 0)}</p>
        <p><b>Size:</b> {album.get('total_size', 0) / (1024 * 1024):.2f} MB</p>
        <p><b>Path:</b> {album.get('path', 'N/A')}</p>
        <p><b>Favorite:</b> {'Yes' if album.get('is_favorite') else 'No'}</p>
        """
        self.metadata_text.setHtml(metadata_html)
        
        # Load and display songs
        self.load_album_songs(album_id)
    
    def on_item_changed(self, item):
        """Handle item changes, especially checkbox clicks"""
        if self._updating_favorites:
            return
        
        # Only process changes to the favorite checkbox column (column 0)
        if item.column() == 0:
            album_id = item.data(Qt.ItemDataRole.UserRole)
            if album_id:
                new_state = item.checkState() == Qt.CheckState.Checked
                try:
                    self.db.set_favorite(album_id, new_state)
                    # Update favorites count
                    self._update_favorites_count()
                    # Refresh details if this album is selected
                    self.on_album_selected()
                except Exception as e:
                    print(f"Error updating favorite: {e}")
                    # Revert checkbox state on error
                    self._updating_favorites = True
                    item.setCheckState(Qt.CheckState.Unchecked if new_state else Qt.CheckState.Checked)
                    self._updating_favorites = False
    
    def toggle_favorite_item(self, item):
        """Toggle favorite when double-clicking (for non-checkbox columns)"""
        # Only toggle if not clicking on checkbox column
        if item.column() != 0:
            row = item.row()
            favorite_item = self.albums_table.item(row, 0)
            if favorite_item:
                album_id = favorite_item.data(Qt.ItemDataRole.UserRole)
                if album_id:
                    current_state = favorite_item.checkState() == Qt.CheckState.Checked
                    new_state = not current_state
                    
                    self._updating_favorites = True
                    favorite_item.setCheckState(Qt.CheckState.Checked if new_state 
                                              else Qt.CheckState.Unchecked)
                    self._updating_favorites = False
                    
                    try:
                        self.db.set_favorite(album_id, new_state)
                        self._update_favorites_count()
                        self.on_album_selected()
                    except Exception as e:
                        print(f"Error updating favorite: {e}")
    
    def _update_favorites_count(self):
        """Update the favorites count label"""
        try:
            all_favorites = self.db.get_all_albums(favorite_only=True)
            favorites_count = len(all_favorites)
            self.favorites_count_label.setText(f"({favorites_count} favorites)")
        except Exception as e:
            print(f"Error updating favorites count: {e}")
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # F key to toggle favorite for selected albums
        shortcut_f = QShortcut(QKeySequence("F"), self)
        shortcut_f.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut_f.activated.connect(self.toggle_selected_favorites)
        
        # Space key to toggle favorite for selected albums (when table has focus)
        shortcut_space = QShortcut(QKeySequence("Space"), self.albums_table)
        shortcut_space.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut_space.activated.connect(self.toggle_selected_favorites)
        
        # Ctrl+F to set all selected albums as favorites
        shortcut_ctrl_f = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut_ctrl_f.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut_ctrl_f.activated.connect(self.set_selected_as_favorites)
        
        # Enter key as alternative to toggle favorites (when table has focus)
        shortcut_enter = QShortcut(QKeySequence("Return"), self.albums_table)
        shortcut_enter.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut_enter.activated.connect(self.toggle_selected_favorites)
    
    def toggle_selected_favorites(self):
        """Toggle favorite status for selected albums"""
        selected_rows = self.albums_table.selectionModel().selectedRows()
        if not selected_rows:
            self.statusBar().showMessage("No albums selected. Select albums first, then press F or Space")
            return
        
        for index in selected_rows:
            row = index.row()
            favorite_item = self.albums_table.item(row, 0)
            if favorite_item:
                album_id = favorite_item.data(Qt.ItemDataRole.UserRole)
                if album_id:
                    current_state = favorite_item.checkState() == Qt.CheckState.Checked
                    new_state = not current_state
                    
                    self._updating_favorites = True
                    favorite_item.setCheckState(Qt.CheckState.Checked if new_state 
                                              else Qt.CheckState.Unchecked)
                    self._updating_favorites = False
                    
                    try:
                        self.db.set_favorite(album_id, new_state)
                    except Exception as e:
                        print(f"Error updating favorite: {e}")
        
        self._update_favorites_count()
        self.on_album_selected()
        self.statusBar().showMessage(f"Toggled favorite for {len(selected_rows)} album(s) - Press F or Space to toggle")
    
    def set_selected_as_favorites(self):
        """Set all selected albums as favorites"""
        selected_rows = self.albums_table.selectionModel().selectedRows()
        if not selected_rows:
            self.statusBar().showMessage("No albums selected. Select albums first, then press Ctrl+F")
            return
        
        for index in selected_rows:
            row = index.row()
            favorite_item = self.albums_table.item(row, 0)
            if favorite_item:
                album_id = favorite_item.data(Qt.ItemDataRole.UserRole)
                if album_id:
                    self._updating_favorites = True
                    favorite_item.setCheckState(Qt.CheckState.Checked)
                    self._updating_favorites = False
                    
                    try:
                        self.db.set_favorite(album_id, True)
                    except Exception as e:
                        print(f"Error updating favorite: {e}")
        
        self._update_favorites_count()
        self.on_album_selected()
        self.statusBar().showMessage(f"Marked {len(selected_rows)} album(s) as favorites - Press Ctrl+F to mark all")
    
    def add_exclude_word(self):
        word = self.exclude_input.text().strip()
        if word:
            self.db.add_exclude_word(word.lower())
            self.exclude_input.clear()
            self.load_exclude_words()
            self.refresh_albums()
    
    def remove_exclude_word(self):
        current_item = self.exclude_list.currentItem()
        if current_item:
            word = current_item.text()
            self.db.remove_exclude_word(word)
            self.load_exclude_words()
            self.refresh_albums()
    
    def load_exclude_words(self):
        self.exclude_list.clear()
        words = self.db.get_exclude_words()
        for word in words:
            self.exclude_list.addItem(word)
    
    def get_exclude_words(self):
        return self.db.get_exclude_words()
    
    def move_selected(self):
        selected_rows = self.albums_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select albums to move")
            return
        
        destination = self.dest_path.text()
        if not destination or not os.path.exists(destination):
            QMessageBox.warning(self, "Error", "Please select a valid destination directory")
            return
        
        album_ids = []
        for index in selected_rows:
            favorite_item = self.albums_table.item(index.row(), 0)
            album_id = favorite_item.data(Qt.ItemDataRole.UserRole)
            album_ids.append(album_id)
        
        reply = QMessageBox.question(
            self, "Confirm Copy", 
            f"Copy {len(album_ids)} album(s) to {destination}?\n\n"
            "(Original files will be preserved)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_move(album_ids, destination)
    
    def move_favorites(self):
        destination = self.dest_path.text()
        if not destination or not os.path.exists(destination):
            QMessageBox.warning(self, "Error", "Please select a valid destination directory")
            return
        
        favorites = self.db.get_all_albums(favorite_only=True)
        if not favorites:
            QMessageBox.information(self, "No Favorites", "No favorite albums selected")
            return
        
        reply = QMessageBox.question(
            self, "Confirm Move", 
            f"Move {len(favorites)} favorite album(s) to {destination}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            album_ids = [a['id'] for a in favorites]
            self.start_move(album_ids, destination)
    
    def copy_favorites_to_location(self):
        """Copy all favorites to the selected destination location"""
        destination = self.dest_path.text()
        if not destination or not os.path.exists(destination):
            QMessageBox.warning(self, "Error", "Please select a valid destination directory")
            return
        
        favorites = self.db.get_all_albums(favorite_only=True)
        if not favorites:
            QMessageBox.information(self, "No Favorites", "No favorite albums selected")
            return
        
        # Calculate total size
        total_size = sum(a.get('total_size', 0) for a in favorites)
        total_size_mb = total_size / (1024 * 1024)
        
        reply = QMessageBox.question(
            self, "Copy Favorites", 
            f"Copy {len(favorites)} favorite album(s) to:\n{destination}\n\n"
            f"Total size: {total_size_mb:.2f} MB\n\n"
            "Original files will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            album_ids = [a['id'] for a in favorites]
            self.start_move(album_ids, destination)
    
    def start_move(self, album_ids, destination):
        self.copy_menu_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(album_ids))
        self.progress_bar.setValue(0)
        
        self.move_thread = MoveThread(self.mover, album_ids, destination)
        self.move_thread.progress.connect(self.on_move_progress)
        self.move_thread.finished.connect(self.on_move_finished)
        self.move_thread.start()
    
    def on_move_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.statusBar().showMessage(f"Copying... {current}/{total}")
    
    def on_move_finished(self, success_count, total, errors, skipped_count=0):
        self.copy_menu_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        message = f"Successfully copied {success_count}/{total} album(s)"
        if skipped_count > 0:
            message += f"\n\nSkipped {skipped_count} album(s) (already exist at destination)"
        if errors:
            message += f"\n\nErrors:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                message += f"\n... and {len(errors) - 10} more"
        
        QMessageBox.information(self, "Copy Complete", message)
        status_msg = f"Copy complete: {success_count} copied"
        if skipped_count > 0:
            status_msg += f", {skipped_count} skipped"
        self.statusBar().showMessage(status_msg)
    
    def export_favorites(self):
        """Export favorites to a JSON file"""
        favorites = self.db.export_favorites()
        
        if not favorites:
            QMessageBox.information(self, "No Favorites", "No favorite albums to export")
            return
        
        # Ask user for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Favorites", "favorites.json", 
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(favorites, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(
                    self, "Export Successful",
                    f"Exported {len(favorites)} favorite album(s) to:\n{file_path}\n\n"
                    "You can import this file after clearing the database."
                )
                self.statusBar().showMessage(f"Exported {len(favorites)} favorites to {file_path}")
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Error",
                    f"Failed to export favorites:\n{str(e)}"
                )
    
    def import_favorites(self):
        """Import favorites from a JSON file"""
        # Ask user for file location
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Favorites", "", 
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                favorites_data = json.load(f)
            
            if not isinstance(favorites_data, list):
                QMessageBox.warning(self, "Invalid File", "JSON file must contain a list of albums")
                return
            
            # Import favorites
            imported_count = self.db.import_favorites(favorites_data)
            
            # Refresh the UI
            self.refresh_albums()
            
            QMessageBox.information(
                self, "Import Successful",
                f"Imported {imported_count} favorite album(s) from:\n{file_path}\n\n"
                f"Total albums in file: {len(favorites_data)}"
            )
            self.statusBar().showMessage(f"Imported {imported_count} favorites from {file_path}")
            
        except FileNotFoundError:
            QMessageBox.warning(self, "File Not Found", f"File not found: {file_path}")
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", f"Invalid JSON file:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(
                self, "Import Error",
                f"Failed to import favorites:\n{str(e)}"
            )
    
    def copy_selected_to_clipboard(self):
        """Copy file paths of selected albums to clipboard"""
        selected_rows = self.albums_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select albums to copy paths")
            return
        
        album_ids = []
        for index in selected_rows:
            favorite_item = self.albums_table.item(index.row(), 0)
            if favorite_item:
                album_id = favorite_item.data(Qt.ItemDataRole.UserRole)
                if album_id:
                    album_ids.append(album_id)
        
        if not album_ids:
            return
        
        # Get all file paths for selected albums
        file_paths = []
        albums = self.db.get_all_albums()
        
        for album_id in album_ids:
            album = next((a for a in albums if a['id'] == album_id), None)
            if album:
                # Get all files for this album
                files = self.db.get_album_files(album_id)
                if files:
                    for file_info in files:
                        file_path = file_info['file_path']
                        if os.path.exists(file_path):
                            file_paths.append(file_path)
                else:
                    # Fallback: use album directory path
                    album_path = album.get('path')
                    if album_path and os.path.exists(album_path):
                        file_paths.append(album_path)
        
        if file_paths:
            # Copy to clipboard (one path per line)
            clipboard_text = '\n'.join(file_paths)
            clipboard = QApplication.clipboard()
            clipboard.setText(clipboard_text)
            # Force clipboard update
            QApplication.processEvents()
            
            # Verify it was copied
            if clipboard.text():
                self.statusBar().showMessage(f"Copied {len(file_paths)} file path(s) to clipboard - Ready to paste (Ctrl+V)")
                QMessageBox.information(
                    self, "Copied to Clipboard", 
                    f"Copied {len(file_paths)} file path(s) to clipboard.\n\n"
                    "You can now paste them using Ctrl+V in:\n"
                    "- File manager\n"
                    "- Terminal\n"
                    "- Text editor\n\n"
                    f"First path: {file_paths[0][:60]}..."
                )
            else:
                QMessageBox.warning(self, "Clipboard Error", "Failed to copy to clipboard. Please try again.")
        else:
            QMessageBox.warning(self, "No Files", "No valid file paths found for selected albums")
    
    def copy_favorites_to_clipboard(self):
        """Copy file paths of all favorite albums to clipboard"""
        favorites = self.db.get_all_albums(favorite_only=True)
        if not favorites:
            QMessageBox.information(self, "No Favorites", "No favorite albums selected")
            return
        
        # Get all file paths for favorite albums
        file_paths = []
        
        for album in favorites:
            album_id = album['id']
            # Get all files for this album
            files = self.db.get_album_files(album_id)
            if files:
                for file_info in files:
                    file_path = file_info['file_path']
                    if os.path.exists(file_path):
                        file_paths.append(file_path)
            else:
                # Fallback: use album directory path
                album_path = album.get('path')
                if album_path and os.path.exists(album_path):
                    file_paths.append(album_path)
        
        if file_paths:
            # Copy to clipboard (one path per line)
            clipboard_text = '\n'.join(file_paths)
            clipboard = QApplication.clipboard()
            clipboard.setText(clipboard_text)
            # Force clipboard update
            QApplication.processEvents()
            
            # Verify it was copied
            if clipboard.text():
                self.statusBar().showMessage(f"Copied {len(file_paths)} file path(s) to clipboard - Ready to paste (Ctrl+V)")
                QMessageBox.information(
                    self, "Copied to Clipboard", 
                    f"Copied {len(file_paths)} file path(s) from {len(favorites)} favorite album(s) to clipboard.\n\n"
                    "You can now paste them using Ctrl+V in:\n"
                    "- File manager\n"
                    "- Terminal\n"
                    "- Text editor\n\n"
                    f"First path: {file_paths[0][:60]}..."
                )
            else:
                QMessageBox.warning(self, "Clipboard Error", "Failed to copy to clipboard. Please try again.")
        else:
            QMessageBox.warning(self, "No Files", "No valid file paths found for favorite albums")
    
    def load_album_songs(self, album_id: int):
        """Load and display songs for the selected album"""
        self.songs_list.clear()
        
        try:
            files = self.db.get_album_files(album_id)
            if not files:
                # If no files in database, try to list files from album directory
                albums = self.db.get_all_albums()
                album = next((a for a in albums if a['id'] == album_id), None)
                if album and album.get('path'):
                    album_path = Path(album['path'])
                    if album_path.exists() and album_path.is_dir():
                        # List audio files from directory
                        audio_extensions = {'.mp3', '.m4a', '.flac', '.wav', '.ogg', '.aac', '.wma'}
                        for file_path in album_path.iterdir():
                            if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
                                files.append({
                                    'file_path': str(file_path),
                                    'file_name': file_path.name,
                                    'file_size': file_path.stat().st_size
                                })
            
            # Sort files by name
            files.sort(key=lambda x: x['file_name'].lower())
            
            for file_info in files:
                file_path = file_info['file_path']
                file_name = file_info['file_name']
                
                # Create widget for each song
                song_widget = QWidget()
                song_layout = QHBoxLayout(song_widget)
                song_layout.setContentsMargins(2, 1, 2, 1)
                song_layout.setSpacing(4)
                
                # Song name label
                song_label = QLabel(file_name)
                song_label.setWordWrap(True)
                song_label.setStyleSheet("""
                    font-size: 12px;
                    padding: 2px;
                    margin: 0px;
                """)
                song_layout.addWidget(song_label, 1)
                
                # Play/Stop button (single button that toggles)
                play_stop_btn = QPushButton("Play")
                play_stop_btn.setMinimumSize(55, 28)
                play_stop_btn.setMaximumSize(55, 28)
                play_stop_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: bold;
                        border: none;
                        padding: 2px 4px;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                    QPushButton:pressed {
                        background-color: #388e3c;
                    }
                """)
                # Store file path and button reference in button's user data
                play_stop_btn.setProperty("file_path", file_path)
                play_stop_btn.setProperty("is_playing", False)
                play_stop_btn.clicked.connect(lambda checked, btn=play_stop_btn: self.toggle_play_stop(btn))
                
                song_layout.addWidget(play_stop_btn)
                
                # Create list item and set widget
                list_item = QListWidgetItem()
                list_item.setSizeHint(song_widget.sizeHint())
                self.songs_list.addItem(list_item)
                self.songs_list.setItemWidget(list_item, song_widget)
                
        except Exception as e:
            print(f"Error loading album songs: {e}")
            import traceback
            traceback.print_exc()
    
    def toggle_play_stop(self, button: QPushButton):
        """Toggle play/stop for a song"""
        if not MULTIMEDIA_AVAILABLE or not self.media_player:
            QMessageBox.information(self, "Audio Playback", 
                                  "Audio playback is not available.\n"
                                  "Please install PyQt6 with multimedia support.")
            return
        
        try:
            is_playing = button.property("is_playing")
            file_path = button.property("file_path")
            
            if is_playing:
                # Currently playing - stop it
                self.stop_current_song()
                button.setText("Play")
                button.setProperty("is_playing", False)
                button.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: bold;
                        border: none;
                        padding: 2px 4px;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                    QPushButton:pressed {
                        background-color: #388e3c;
                    }
                """)
            else:
                # Not playing - start playing
                # Stop currently playing song if any
                if self.currently_playing_item and self.currently_playing_item != button:
                    self.stop_current_song()
                
                # Check if file exists
                if not os.path.exists(file_path):
                    QMessageBox.warning(self, "File Not Found", f"Audio file not found:\n{file_path}")
                    return
                
                # Set source and play
                self.media_player.setSource(QUrl.fromLocalFile(file_path))
                self.media_player.play()
                
                # Update button to show it's playing
                button.setText("Stop")
                button.setProperty("is_playing", True)
                button.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: bold;
                        border: none;
                        padding: 2px 4px;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #da190b;
                    }
                    QPushButton:pressed {
                        background-color: #c62828;
                    }
                """)
                self.currently_playing_item = button
                
        except Exception as e:
            print(f"Error toggling play/stop: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Playback Error", f"Could not play audio file:\n{str(e)}")
    
    def stop_current_song(self):
        """Stop currently playing song"""
        if MULTIMEDIA_AVAILABLE and self.media_player:
            try:
                self.media_player.stop()
                if self.currently_playing_item:
                    self.currently_playing_item.setText("Play")
                    self.currently_playing_item.setProperty("is_playing", False)
                    self.currently_playing_item.setStyleSheet("""
                        QPushButton {
                            background-color: #4CAF50;
                            color: white;
                            border-radius: 5px;
                            font-size: 12px;
                            font-weight: bold;
                            border: none;
                        }
                        QPushButton:hover {
                            background-color: #45a049;
                        }
                        QPushButton:pressed {
                            background-color: #388e3c;
                        }
                    """)
                    self.currently_playing_item = None
            except Exception as e:
                print(f"Error stopping song: {e}")
    
    def on_song_clicked(self, item):
        """Handle song click to show metadata"""
        try:
            # Get the widget from the list item
            widget = self.songs_list.itemWidget(item)
            if widget:
                # Find the song label to get file info
                song_label = widget.findChild(QLabel)
                if song_label:
                    file_name = song_label.text()
                    
                    # Find the play button to get file path
                    play_btn = widget.findChild(QPushButton)
                    if play_btn:
                        file_path = play_btn.property("file_path")
                        if file_path:
                            self.show_file_metadata(file_path, file_name)
        except Exception as e:
            print(f"Error handling song click: {e}")
            import traceback
            traceback.print_exc()
    
    def show_file_metadata(self, file_path: str, file_name: str):
        """Extract and display detailed metadata from audio file"""
        try:
            from mutagen import File as MutagenFile
            from mutagen.id3 import ID3
            from mutagen.mp4 import MP4
            from mutagen.flac import FLAC
            
            # Show the sidebar
            self.file_metadata_sidebar.setVisible(True)
            
            # Check if file exists
            if not os.path.exists(file_path):
                self.file_metadata_content.setHtml(f"<p><b>Error:</b> File not found</p><p>{file_path}</p>")
                return
            
            # Get file size
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            # Load audio file
            audio = MutagenFile(file_path)
            
            if audio is None:
                self.file_metadata_content.setHtml(f"<p><b>Error:</b> Could not read audio file</p><p>{file_name}</p>")
                return
            
            # Build metadata HTML
            html = f"<h3 style='color: #4CAF50; margin-top: 0;'>{file_name}</h3>"
            html += "<hr style='border: 1px solid #ddd;'>"
            
            # Basic file info
            html += "<h4 style='color: #333; margin-bottom: 5px;'>📁 File Information</h4>"
            html += f"<p style='margin: 3px 0;'><b>Path:</b> {file_path}</p>"
            html += f"<p style='margin: 3px 0;'><b>Size:</b> {file_size_mb:.2f} MB ({file_size:,} bytes)</p>"
            
            # Audio properties
            if hasattr(audio, 'info') and audio.info:
                html += "<h4 style='color: #333; margin-top: 15px; margin-bottom: 5px;'>🎵 Audio Properties</h4>"
                
                # Duration
                if hasattr(audio.info, 'length'):
                    duration = int(audio.info.length)
                    minutes = duration // 60
                    seconds = duration % 60
                    html += f"<p style='margin: 3px 0;'><b>Duration:</b> {minutes}:{seconds:02d} ({duration} seconds)</p>"
                
                # Bitrate
                if hasattr(audio.info, 'bitrate'):
                    bitrate_kbps = audio.info.bitrate / 1000
                    html += f"<p style='margin: 3px 0;'><b>Bitrate:</b> {bitrate_kbps:.0f} kbps</p>"
                
                # Sample rate
                if hasattr(audio.info, 'sample_rate'):
                    html += f"<p style='margin: 3px 0;'><b>Sample Rate:</b> {audio.info.sample_rate} Hz</p>"
                
                # Channels
                if hasattr(audio.info, 'channels'):
                    channels_text = "Stereo" if audio.info.channels == 2 else f"{audio.info.channels} channels"
                    html += f"<p style='margin: 3px 0;'><b>Channels:</b> {channels_text}</p>"
                
                # Bits per sample (for FLAC)
                if hasattr(audio.info, 'bits_per_sample'):
                    html += f"<p style='margin: 3px 0;'><b>Bits per Sample:</b> {audio.info.bits_per_sample} bit</p>"
                
                # Codec info
                if hasattr(audio.info, 'codec'):
                    html += f"<p style='margin: 3px 0;'><b>Codec:</b> {audio.info.codec}</p>"
                elif hasattr(audio.info, 'codec_name'):
                    html += f"<p style='margin: 3px 0;'><b>Codec:</b> {audio.info.codec_name}</p>"
            
            # Extract and display album art if available
            album_art_data = None
            try:
                from mutagen.id3 import APIC
                from mutagen.mp4 import MP4Cover
                import base64
                
                # Try to extract album art
                if hasattr(audio, 'tags') and audio.tags:
                    # For MP3 (ID3)
                    if 'APIC:' in audio.tags or any(k.startswith('APIC') for k in audio.tags.keys()):
                        for key in audio.tags.keys():
                            if key.startswith('APIC'):
                                apic = audio.tags[key]
                                if hasattr(apic, 'data'):
                                    album_art_data = apic.data
                                    break
                    # For M4A (MP4)
                    elif 'covr' in audio.tags:
                        covr = audio.tags['covr']
                        if isinstance(covr, list) and len(covr) > 0:
                            album_art_data = bytes(covr[0])
                        elif isinstance(covr, bytes):
                            album_art_data = covr
                    # For FLAC
                    elif hasattr(audio, 'pictures') and audio.pictures:
                        album_art_data = audio.pictures[0].data
                
                # Display album art if found
                if album_art_data:
                    # Convert to base64 for HTML display
                    art_base64 = base64.b64encode(album_art_data).decode('utf-8')
                    html += "<h4 style='color: #333; margin-top: 15px; margin-bottom: 5px;'>🖼️ Album Art</h4>"
                    html += f"<img src='data:image/jpeg;base64,{art_base64}' style='max-width: 100%; max-height: 200px; border: 1px solid #ddd; border-radius: 4px; margin: 5px 0;' />"
            except Exception as e:
                print(f"Could not extract album art: {e}")
            
            # Tags/Metadata
            if audio.tags:
                html += "<h4 style='color: #333; margin-top: 15px; margin-bottom: 5px;'>🏷️ Tags</h4>"
                
                # Binary/image fields to skip
                binary_fields = {
                    'APIC', 'APIC:', 'covr', 'PICTURE', 'metadata_block_picture',
                    'GEOB', 'PRIV', 'UFID'  # Other binary ID3 frames
                }
                
                # Common tags to display
                tag_mappings = {
                    # ID3 tags (MP3)
                    'TIT2': 'Title',
                    'TPE1': 'Artist',
                    'TALB': 'Album',
                    'TPE2': 'Album Artist',
                    'TDRC': 'Year',
                    'TCON': 'Genre',
                    'TRCK': 'Track Number',
                    'TPOS': 'Disc Number',
                    'COMM': 'Comment',
                    'TCOM': 'Composer',
                    'TPUB': 'Publisher',
                    'TCOP': 'Copyright',
                    # MP4 tags (M4A)
                    '\xa9nam': 'Title',
                    '\xa9ART': 'Artist',
                    '\xa9alb': 'Album',
                    'aART': 'Album Artist',
                    '\xa9day': 'Year',
                    '\xa9gen': 'Genre',
                    'trkn': 'Track Number',
                    'disk': 'Disc Number',
                    '\xa9cmt': 'Comment',
                    '\xa9wrt': 'Composer',
                    # FLAC/Vorbis tags
                    'title': 'Title',
                    'artist': 'Artist',
                    'album': 'Album',
                    'albumartist': 'Album Artist',
                    'date': 'Year',
                    'genre': 'Genre',
                    'tracknumber': 'Track Number',
                    'discnumber': 'Disc Number',
                    'comment': 'Comment',
                    'composer': 'Composer',
                }
                
                # Display tags
                displayed_tags = set()
                for tag_key, tag_value in audio.tags.items():
                    # Skip binary fields (album art, etc.)
                    if any(tag_key.startswith(bf) for bf in binary_fields):
                        continue
                    
                    # Check if value is binary data
                    is_binary = False
                    if isinstance(tag_value, bytes):
                        is_binary = True
                    elif hasattr(tag_value, 'data') and isinstance(tag_value.data, bytes):
                        is_binary = True
                    
                    # Skip binary data
                    if is_binary:
                        continue
                    
                    # Get friendly name
                    friendly_name = tag_mappings.get(tag_key, tag_key)
                    
                    # Skip if already displayed
                    if friendly_name in displayed_tags:
                        continue
                    
                    # Format value
                    try:
                        if hasattr(tag_value, 'text'):
                            # ID3 tags
                            value_str = ', '.join(str(v) for v in tag_value.text)
                        elif isinstance(tag_value, (list, tuple)):
                            # MP4/FLAC tags - check if it's not binary
                            if all(not isinstance(v, bytes) for v in tag_value):
                                value_str = ', '.join(str(v) for v in tag_value)
                            else:
                                continue  # Skip binary lists
                        else:
                            value_str = str(tag_value)
                        
                        # Skip empty values
                        if value_str and value_str.strip():
                            html += f"<p style='margin: 3px 0;'><b>{friendly_name}:</b> {value_str}</p>"
                            displayed_tags.add(friendly_name)
                    except Exception as e:
                        # Skip tags that can't be converted to string
                        print(f"Skipping tag {tag_key}: {e}")
                        continue
                
                # If no tags were displayed
                if not displayed_tags:
                    html += "<p style='margin: 3px 0; color: #666;'><i>No tags found</i></p>"
            else:
                html += "<h4 style='color: #333; margin-top: 15px; margin-bottom: 5px;'>🏷️ Tags</h4>"
                html += "<p style='margin: 3px 0; color: #666;'><i>No tags available</i></p>"
            
            # Set the HTML content
            self.file_metadata_content.setHtml(html)
            
        except Exception as e:
            print(f"Error extracting metadata: {e}")
            import traceback
            traceback.print_exc()
            self.file_metadata_content.setHtml(
                f"<h3 style='color: #f44336;'>Error</h3>"
                f"<p>Could not extract metadata from file:</p>"
                f"<p><b>{file_name}</b></p>"
                f"<p style='color: #666; font-size: 11px;'>{str(e)}</p>"
            )
    
    def hide_file_metadata_sidebar(self):
        """Hide the file metadata sidebar"""
        self.file_metadata_sidebar.setVisible(False)


def main():
    app = QApplication(sys.argv)
    window = AlbumSelectionApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

