# Local Music Collection Curator

A Python Qt application for filtering, selecting, and moving favorite music albums from a large collection to a pendrive or mounted location.

## Screenshots

![Main Window Placeholder](screenshots/main-window.png)
*Application Main Window*

## Features

- **Album Scanning**: Scan large music directories and extract album metadata
- **SQLite Database**: Store album information for fast filtering and searching
- **Exclude Words**: Filter out albums containing specific words (e.g., devotional, bakthi)
- **Favorite Selection**: Mark albums as favorites and filter by favorites
- **Move Albums**: Copy selected or favorite albums to pendrive/mounted location
- **Progress Tracking**: Real-time progress bars for scanning and moving operations

## Requirements

- Python 3.8+
- PyQt6
- mutagen (for audio metadata extraction)

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python main.py
```

2. **Set Source Directory**: 
   - Default is set to `/media/vinay-vengala/Seagate Backup Plus Drive/JioSaavn-Songs`
   - Click "Browse" to select a different source directory

3. **Scan Albums**:
   - Click "Scan Albums" to scan the source directory
   - The application will extract album metadata and store it in SQLite database
   - Progress will be shown in the status bar

4. **Add Exclude Words**:
   - Enter words in the "Exclude Words" section (e.g., "devotional", "bakthi")
   - Click "Add" to add them to the exclude list
   - Albums containing these words will be filtered out

5. **Mark Favorites**:
   - Double-click on an album row to toggle favorite status
   - Or use the checkbox in the "Favorite" column
   - Check "Show Favorites Only" to filter the list

6. **Move Albums**:
   - Select destination directory (pendrive/mounted location)
   - Select albums in the table and click "Move Selected"
   - Or click "Move All Favorites" to move all favorite albums

## Database

The application uses SQLite database (`albums.db`) to store:
- Album information (name, artist, year, genre, path, size)
- File listings for each album
- Exclude words
- Favorite status

## Supported Audio Formats

- MP3
- FLAC
- M4A
- OGG
- WAV
- AAC

## Notes

- The application copies files (does not delete originals)
- Large collections may take time to scan initially
- Make sure destination has enough space before moving albums

