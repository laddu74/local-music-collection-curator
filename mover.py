"""
Module for moving albums to destination (pendrive/mounted location)
"""
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from database import AlbumDatabase


class AlbumMover:
    def __init__(self, db: AlbumDatabase):
        self.db = db
    
    def _is_mtp_path(self, path: str) -> bool:
        """Check if path is on an MTP-mounted device"""
        return '/gvfs/' in str(path) or '/mtp:' in str(path) or '/run/user/' in str(path)
    
    def _safe_copy_file(self, source: Path, dest: Path) -> bool:
        """Copy file with fallback for MTP devices"""
        # Ensure destination directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # For MTP paths, use chunked read/write
        if self._is_mtp_path(str(source)):
            try:
                # Read and write in chunks for MTP devices
                chunk_size = 1024 * 1024  # 1MB chunks
                with open(source, 'rb') as src_file:
                    with open(dest, 'wb') as dst_file:
                        while True:
                            chunk = src_file.read(chunk_size)
                            if not chunk:
                                break
                            dst_file.write(chunk)
                return True
            except Exception as e:
                # If chunked copy fails, try shutil.copy
                try:
                    shutil.copy(source, dest)
                    return True
                except Exception as e2:
                    print(f"Error copying {source} to {dest}: {e2}")
                    return False
        else:
            # For regular filesystems, try copy2 first
            try:
                shutil.copy2(source, dest)
                return True
            except (OSError, IOError) as e:
                # Fallback to simple copy
                try:
                    shutil.copy(source, dest)
                    return True
                except Exception as e2:
                    print(f"Error copying {source} to {dest}: {e2}")
                    return False
    
    def move_album(self, album_id: int, destination: str, 
                  progress_callback=None) -> Tuple[bool, str]:
        """
        Move an album to destination
        Returns (success, message)
        """
        albums = self.db.get_all_albums()
        album = next((a for a in albums if a['id'] == album_id), None)
        
        if not album:
            return False, "Album not found"
        
        source_path = Path(album['path'])
        if not source_path.exists():
            return False, f"Source path does not exist: {source_path}"
        
        dest_path = Path(destination)
        if not dest_path.exists():
            try:
                dest_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"Cannot create destination: {e}"
        
        # Create album directory in destination
        album_dest = dest_path / source_path.name
        
        try:
            # Check if destination already exists
            if album_dest.exists():
                # Check if it's actually the same directory (source == destination)
                try:
                    if album_dest.resolve() == source_path.resolve():
                        return False, f"Source and destination are the same: {album_dest}"
                except:
                    pass
                
                # For MTP devices or if destination exists, skip it
                # Return a special message indicating it was skipped
                return False, f"Destination already exists (skipped): {album_dest}"
            
            # Get all files for this album
            files = self.db.get_album_files(album_id)
            
            if not files:
                # Fallback: copy entire directory
                try:
                    shutil.copytree(source_path, album_dest)
                except (OSError, IOError) as e:
                    # If copytree fails (e.g., MTP), copy files individually
                    if 'Operation not supported' in str(e) or self._is_mtp_path(str(source_path)):
                        album_dest.mkdir(parents=True, exist_ok=True)
                        for item in source_path.iterdir():
                            if item.is_file():
                                dest_item = album_dest / item.name
                                if not self._safe_copy_file(item, dest_item):
                                    raise Exception(f"Failed to copy {item.name}")
                            elif item.is_dir():
                                # Recursively copy subdirectories
                                sub_dest = album_dest / item.name
                                sub_dest.mkdir(parents=True, exist_ok=True)
                                for sub_item in item.rglob('*'):
                                    if sub_item.is_file():
                                        rel_path = sub_item.relative_to(item)
                                        dest_sub_item = sub_dest / rel_path
                                        dest_sub_item.parent.mkdir(parents=True, exist_ok=True)
                                        if not self._safe_copy_file(sub_item, dest_sub_item):
                                            raise Exception(f"Failed to copy {sub_item.name}")
                    else:
                        raise
            else:
                # Copy individual files
                album_dest.mkdir(parents=True, exist_ok=True)
                for i, file_info in enumerate(files):
                    source_file = Path(file_info['file_path'])
                    if source_file.exists():
                        dest_file = album_dest / file_info['file_name']
                        if not self._safe_copy_file(source_file, dest_file):
                            raise Exception(f"Failed to copy {file_info['file_name']}")
                    
                    if progress_callback:
                        progress_callback(i + 1, len(files))
            
            return True, f"Successfully moved to {album_dest}"
            
        except Exception as e:
            return False, f"Error moving album: {e}"
    
    def move_favorites(self, destination: str, 
                      progress_callback=None) -> Tuple[int, int, List[str], int]:
        """
        Move all favorite albums to destination
        Returns (success_count, total_count, error_messages, skipped_count)
        """
        favorites = self.db.get_all_albums(favorite_only=True)
        total = len(favorites)
        success_count = 0
        skipped_count = 0
        errors = []
        
        for i, album in enumerate(favorites):
            success, message = self.move_album(album['id'], destination, 
                                             lambda curr, total: None)
            if success:
                success_count += 1
            elif "already exists" in message.lower() or "skipped" in message.lower():
                skipped_count += 1
                # Don't add to errors if it's just skipped (already exists)
            else:
                errors.append(f"{album['album_name']}: {message}")
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        return success_count, total, errors, skipped_count
    
    def get_destination_size(self, destination: str) -> int:
        """Get available space in destination (in bytes)"""
        try:
            stat = os.statvfs(destination)
            return stat.f_bavail * stat.f_frsize
        except:
            return 0
    
    def estimate_required_space(self, album_ids: List[int]) -> int:
        """Estimate total space required for albums (in bytes)"""
        total_size = 0
        albums = self.db.get_all_albums()
        
        for album_id in album_ids:
            album = next((a for a in albums if a['id'] == album_id), None)
            if album:
                total_size += album['total_size']
        
        return total_size

