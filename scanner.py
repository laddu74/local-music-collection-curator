"""
Album scanner module to scan music directory and populate database
"""
import os
import base64
from pathlib import Path
from mutagen import File
from mutagen.id3 import ID3NoHeaderError
from mutagen.id3 import APIC
from mutagen.mp4 import MP4Cover
from PIL import Image
from io import BytesIO
from database import AlbumDatabase
from typing import Dict, Optional


class AlbumScanner:
    def __init__(self, db: AlbumDatabase):
        self.db = db
        self.supported_formats = {'.mp3', '.flac', '.m4a', '.ogg', '.wav', '.aac'}
    
    def get_audio_metadata(self, file_path: str) -> Dict[str, Optional[str]]:
        """Extract metadata from audio file"""
        metadata = {
            'album': None,
            'artist': None,
            'year': None,
            'genre': None,
            'title': None,
            'track': None
        }
        
        try:
            audio_file = File(file_path)
            if audio_file is None:
                return metadata
            
            # Try to get album
            if hasattr(audio_file, 'get') and audio_file.get('TALB'):
                metadata['album'] = str(audio_file.get('TALB')[0])
            elif 'TALB' in audio_file:
                metadata['album'] = str(audio_file['TALB'][0])
            elif hasattr(audio_file, 'tags') and audio_file.tags:
                if 'TALB' in audio_file.tags:
                    metadata['album'] = str(audio_file.tags['TALB'][0])
            
            # Try to get artist
            if hasattr(audio_file, 'get') and audio_file.get('TPE1'):
                metadata['artist'] = str(audio_file.get('TPE1')[0])
            elif 'TPE1' in audio_file:
                metadata['artist'] = str(audio_file['TPE1'][0])
            elif hasattr(audio_file, 'tags') and audio_file.tags:
                if 'TPE1' in audio_file.tags:
                    metadata['artist'] = str(audio_file.tags['TPE1'][0])
            
            # Try to get title
            if hasattr(audio_file, 'get') and audio_file.get('TIT2'):
                metadata['title'] = str(audio_file.get('TIT2')[0])
            elif 'TIT2' in audio_file:
                metadata['title'] = str(audio_file['TIT2'][0])
            elif hasattr(audio_file, 'tags') and audio_file.tags:
                if 'TIT2' in audio_file.tags:
                    metadata['title'] = str(audio_file.tags['TIT2'][0])
            
            # Try to get track number
            if hasattr(audio_file, 'get') and audio_file.get('TRCK'):
                try:
                    track_str = str(audio_file.get('TRCK')[0])
                    metadata['track'] = track_str.split('/')[0] if '/' in track_str else track_str
                except:
                    pass
            elif 'TRCK' in audio_file:
                try:
                    track_str = str(audio_file['TRCK'][0])
                    metadata['track'] = track_str.split('/')[0] if '/' in track_str else track_str
                except:
                    pass
            
            # Try to get year
            if hasattr(audio_file, 'get') and audio_file.get('TDRC'):
                year_str = str(audio_file.get('TDRC')[0])
                try:
                    metadata['year'] = int(year_str[:4])
                except:
                    pass
            elif 'TDRC' in audio_file:
                year_str = str(audio_file['TDRC'][0])
                try:
                    metadata['year'] = int(year_str[:4])
                except:
                    pass
            
            # Try to get genre
            if hasattr(audio_file, 'get') and audio_file.get('TCON'):
                metadata['genre'] = str(audio_file.get('TCON')[0])
            elif 'TCON' in audio_file:
                metadata['genre'] = str(audio_file['TCON'][0])
            
        except ID3NoHeaderError:
            pass
        except Exception as e:
            print(f"Error reading metadata from {file_path}: {e}")
        
        return metadata
    
    def extract_album_art(self, file_path: str) -> Optional[str]:
        """Extract album art from audio file and save as thumbnail"""
        try:
            audio_file = File(file_path)
            if audio_file is None:
                return None
            
            # Try to get embedded album art
            tags = getattr(audio_file, 'tags', None)
            if tags is not None:
                # MP3 files
                if 'APIC:' in tags:
                    apic = tags['APIC:'].data
                    return self._save_thumbnail(apic, file_path)
                # FLAC files
                elif 'PICTURE' in tags:
                    picture = tags['PICTURE'][0]
                    return self._save_thumbnail(picture.data, file_path)
            
            # MP4/M4A files - check directly in audio_file
            if hasattr(audio_file, 'get') and audio_file.get('covr'):
                try:
                    cover = audio_file['covr'][0]
                    if isinstance(cover, MP4Cover):
                        # MP4Cover has image data directly
                        return self._save_thumbnail(bytes(cover), file_path)
                except (KeyError, IndexError, TypeError):
                    pass
            
        except Exception as e:
            print(f"Error extracting album art from {file_path}: {e}")
        
        return None
    
    def _save_thumbnail(self, image_data: bytes, source_file: str) -> Optional[str]:
        """Save thumbnail image to a temporary location"""
        try:
            # Create thumbnails directory
            thumb_dir = Path("thumbnails")
            thumb_dir.mkdir(exist_ok=True)
            
            # Generate thumbnail filename based on source file
            source_hash = hash(source_file) % (10 ** 8)
            thumb_path = thumb_dir / f"thumb_{source_hash}.jpg"
            
            # Load and resize image
            img = Image.open(BytesIO(image_data))
            img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            img.convert('RGB').save(thumb_path, 'JPEG', quality=85)
            
            return str(thumb_path)
        except Exception as e:
            print(f"Error saving thumbnail: {e}")
            return None
    
    def find_folder_cover(self, folder_path: str) -> Optional[str]:
        """Find cover image in folder (cover.jpg, folder.jpg, etc.)"""
        cover_names = ['cover.jpg', 'folder.jpg', 'album.jpg', 'artwork.jpg', 
                      'cover.png', 'folder.png', 'album.png', 'artwork.png',
                      'Cover.jpg', 'Folder.jpg', 'Album.jpg', 'Artwork.jpg']
        
        folder = Path(folder_path)
        for cover_name in cover_names:
            cover_path = folder / cover_name
            if cover_path.exists():
                # Create thumbnail from folder image
                try:
                    thumb_dir = Path("thumbnails")
                    thumb_dir.mkdir(exist_ok=True)
                    
                    source_hash = hash(str(cover_path)) % (10 ** 8)
                    thumb_path = thumb_dir / f"thumb_{source_hash}.jpg"
                    
                    img = Image.open(cover_path)
                    img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                    img.convert('RGB').save(thumb_path, 'JPEG', quality=85)
                    
                    return str(thumb_path)
                except Exception as e:
                    print(f"Error creating thumbnail from folder image: {e}")
                    return str(cover_path)  # Return original path as fallback
        
        return None
    
    def scan_directory(self, root_path: str, progress_callback=None) -> int:
        """
        Scan directory for albums and populate database
        Returns count of albums found
        """
        root = Path(root_path)
        if not root.exists():
            raise ValueError(f"Directory does not exist: {root_path}")
        
        albums_found = {}
        total_files = 0
        
        # Walk through directory
        for root_dir, dirs, files in os.walk(root_path):
            # Check if this directory contains audio files
            audio_files = [f for f in files 
                          if Path(f).suffix.lower() in self.supported_formats]
            
            if not audio_files:
                continue
            
            # Use directory name as album name if metadata not available
            dir_name = Path(root_dir).name
            album_name = dir_name
            artist = None
            year = None
            genre = None
            
            # Try to get metadata from first file
            first_file = os.path.join(root_dir, audio_files[0])
            metadata = self.get_audio_metadata(first_file)
            
            if metadata['album']:
                album_name = metadata['album']
            if metadata['artist']:
                artist = metadata['artist']
            if metadata['year']:
                year = metadata['year']
            if metadata['genre']:
                genre = metadata['genre']
            
            # Try to find album art
            thumbnail_path = None
            # First try to extract from audio file
            thumbnail_path = self.extract_album_art(first_file)
            # If not found, try to find in folder
            if not thumbnail_path:
                thumbnail_path = self.find_folder_cover(root_dir)
            
            # Calculate total size and file count
            total_size = 0
            file_count = 0
            
            for audio_file in audio_files:
                file_path = os.path.join(root_dir, audio_file)
                try:
                    file_size = os.path.getsize(file_path)
                    total_size += file_size
                    file_count += 1
                    total_files += 1
                except:
                    pass
            
            # Store album info
            if album_name not in albums_found:
                albums_found[album_name] = {
                    'path': root_dir,
                    'artist': artist,
                    'year': year,
                    'genre': genre,
                    'file_count': file_count,
                    'total_size': total_size,
                    'thumbnail_path': thumbnail_path,
                    'files': []
                }
            else:
                albums_found[album_name]['file_count'] += file_count
                albums_found[album_name]['total_size'] += total_size
                # Update thumbnail if not already set
                if not albums_found[album_name].get('thumbnail_path') and thumbnail_path:
                    albums_found[album_name]['thumbnail_path'] = thumbnail_path
            
            # Store file paths
            for audio_file in audio_files:
                file_path = os.path.join(root_dir, audio_file)
                try:
                    file_size = os.path.getsize(file_path)
                    albums_found[album_name]['files'].append({
                        'path': file_path,
                        'name': audio_file,
                        'size': file_size
                    })
                except:
                    pass
            
            # Progress callback
            if progress_callback:
                progress_callback(total_files, len(albums_found))
        
        # Add albums to database
        for album_name, album_info in albums_found.items():
            album_id = self.db.add_album(
                album_name=album_name,
                path=album_info['path'],
                artist=album_info['artist'],
                year=album_info['year'],
                genre=album_info['genre'],
                file_count=album_info['file_count'],
                total_size=album_info['total_size'],
                thumbnail_path=album_info.get('thumbnail_path')
            )
            
            # Add files to database
            if album_id:
                for file_info in album_info['files']:
                    self.db.add_file_to_album(
                        album_id=album_id,
                        file_path=file_info['path'],
                        file_name=file_info['name'],
                        file_size=file_info['size']
                    )
        
        return len(albums_found)

