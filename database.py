"""
SQLite database module for album management
"""
import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Optional


class AlbumDatabase:
    def __init__(self, db_path: str = "albums.db"):
        self.db_path = db_path
        self.init_database()
    
    def _get_connection(self):
        """Get database connection with timeout to handle locking"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Enable WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Albums table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_name TEXT NOT NULL,
                artist TEXT,
                year INTEGER,
                genre TEXT,
                path TEXT UNIQUE NOT NULL,
                file_count INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0,
                thumbnail_path TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add thumbnail_path column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE albums ADD COLUMN thumbnail_path TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Exclude words table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exclude_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE NOT NULL
            )
        """)
        
        # Files table for tracking individual files
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS album_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_id INTEGER,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                FOREIGN KEY (album_id) REFERENCES albums(id)
            )
        """)
        
        # Source directories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_directories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_album(self, album_name: str, path: str, artist: str = None, 
                  year: int = None, genre: str = None, file_count: int = 0, 
                  total_size: int = 0, thumbnail_path: str = None) -> int:
        """Add an album to the database"""
        max_retries = 3
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO albums 
                    (album_name, artist, year, genre, path, file_count, total_size, thumbnail_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (album_name, artist, year, genre, path, file_count, total_size, thumbnail_path))
                
                album_id = cursor.lastrowid
                conn.commit()
                conn.close()
                return album_id
            except sqlite3.OperationalError as e:
                if conn:
                    conn.close()
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Error adding album: {e}")
                return None
            except sqlite3.Error as e:
                if conn:
                    conn.close()
                print(f"Error adding album: {e}")
                return None
            except Exception as e:
                if conn:
                    conn.close()
                print(f"Unexpected error adding album: {e}")
                return None
        return None
    
    def add_file_to_album(self, album_id: int, file_path: str, file_name: str, file_size: int):
        """Add a file to an album"""
        max_retries = 3
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR IGNORE INTO album_files (album_id, file_path, file_name, file_size)
                    VALUES (?, ?, ?, ?)
                """, (album_id, file_path, file_name, file_size))
                conn.commit()
                conn.close()
                return
            except sqlite3.OperationalError as e:
                if conn:
                    conn.close()
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))
                    continue
                print(f"Error adding file: {e}")
                return
            except sqlite3.Error as e:
                if conn:
                    conn.close()
                print(f"Error adding file: {e}")
                return
            except Exception as e:
                if conn:
                    conn.close()
                print(f"Unexpected error adding file: {e}")
                return
    
    def get_all_albums(self, exclude_words: List[str] = None, 
                      favorite_only: bool = False) -> List[Dict]:
        """Get all albums with optional filtering"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self._get_connection()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = "SELECT * FROM albums WHERE 1=1"
                params = []
                
                if favorite_only:
                    query += " AND is_favorite = 1"
                
                if exclude_words:
                    # Filter out albums containing exclude words in name or artist
                    # Use COALESCE to handle NULL values and LOWER for case-insensitive matching
                    exclude_conditions = []
                    for word in exclude_words:
                        word_lower = word.lower()
                        exclude_conditions.append(
                            "(LOWER(COALESCE(album_name, '')) NOT LIKE ? AND LOWER(COALESCE(artist, '')) NOT LIKE ?)"
                        )
                        params.extend([f"%{word_lower}%", f"%{word_lower}%"])
                    
                    if exclude_conditions:
                        query += " AND " + " AND ".join(exclude_conditions)
                
                query += " ORDER BY album_name"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                conn.close()
                return result
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    conn.close()
                    raise
            except Exception as e:
                if 'conn' in locals():
                    conn.close()
                raise
    
    def toggle_favorite(self, album_id: int) -> bool:
        """Toggle favorite status of an album"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT is_favorite FROM albums WHERE id = ?", (album_id,))
            result = cursor.fetchone()
            if result:
                new_status = 1 if result[0] == 0 else 0
                cursor.execute("UPDATE albums SET is_favorite = ? WHERE id = ?", 
                             (new_status, album_id))
                conn.commit()
                return new_status == 1
        except sqlite3.Error as e:
            print(f"Error toggling favorite: {e}")
            return False
        finally:
            conn.close()
    
    def set_favorite(self, album_id: int, is_favorite: bool):
        """Set favorite status of an album"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("UPDATE albums SET is_favorite = ? WHERE id = ?", 
                         (1 if is_favorite else 0, album_id))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error setting favorite: {e}")
        finally:
            conn.close()
    
    def add_exclude_word(self, word: str):
        """Add an exclude word"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("INSERT OR IGNORE INTO exclude_words (word) VALUES (?)", (word,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error adding exclude word: {e}")
        finally:
            conn.close()
    
    def get_exclude_words(self) -> List[str]:
        """Get all exclude words"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT word FROM exclude_words ORDER BY word")
        words = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return words
    
    def remove_exclude_word(self, word: str):
        """Remove an exclude word"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM exclude_words WHERE word = ?", (word,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error removing exclude word: {e}")
        finally:
            conn.close()
    
    def get_album_files(self, album_id: int) -> List[Dict]:
        """Get all files for an album"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM album_files WHERE album_id = ?", (album_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def clear_database(self):
        """Clear all data from database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM album_files")
        cursor.execute("DELETE FROM albums")
        conn.commit()
        conn.close()
    
    def add_source_directory(self, path: str) -> bool:
        """Add a source directory"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("INSERT OR IGNORE INTO source_directories (path) VALUES (?)", (path,))
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error as e:
            conn.close()
            print(f"Error adding source directory: {e}")
            return False
    
    def get_source_directories(self) -> List[str]:
        """Get all source directories"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT path FROM source_directories ORDER BY added_at")
        paths = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return paths
    
    def remove_source_directory(self, path: str):
        """Remove a source directory"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM source_directories WHERE path = ?", (path,))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Error removing source directory: {e}")
        finally:
            conn.close()
    
    def export_favorites(self) -> List[Dict]:
        """Export favorite albums as a list of dictionaries"""
        favorites = self.get_all_albums(favorite_only=True)
        export_data = []
        
        for album in favorites:
            export_data.append({
                'album_name': album.get('album_name'),
                'artist': album.get('artist'),
                'path': album.get('path'),
                'year': album.get('year'),
                'genre': album.get('genre')
            })
        
        return export_data
    
    def import_favorites(self, favorites_data: List[Dict]) -> int:
        """Import favorites by matching album paths and names"""
        imported_count = 0
        
        for fav_data in favorites_data:
            # Try to find album by path first
            albums = self.get_all_albums()
            album = next((a for a in albums 
                         if a.get('path') == fav_data.get('path')), None)
            
            # If not found by path, try by name and artist
            if not album:
                album = next((a for a in albums 
                             if a.get('album_name') == fav_data.get('album_name') 
                             and a.get('artist') == fav_data.get('artist')), None)
            
            if album:
                self.set_favorite(album['id'], True)
                imported_count += 1
        
        return imported_count

