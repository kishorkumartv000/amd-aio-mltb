import os
import shutil
import zipfile
import asyncio
from config import Config
from bot.helpers.utils import create_apple_zip, format_string, send_message, edit_message, zip_handler, MAX_SIZE
from bot.logger import LOGGER
from mutagen import File
from mutagen.mp4 import MP4
import re
from bot.settings import bot_set
from bot.helpers.progress import ProgressReporter
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- Uploader Listener ---

class UploaderListener:
    def __init__(self, user, path, name):
        self.user = user
        self.path = path
        self.name = name
        self.is_cancelled = False

    async def on_upload_complete(self, link, files, folders, mime_type, dir_id):
        LOGGER.info(f"Upload complete for {self.user['user_id']}: {link}")
        await send_message(self.user, f"✅ **Upload Complete!**\n\n**Link:** {link}")

    async def on_upload_error(self, error):
        LOGGER.error(f"Upload error for {self.user['user_id']}: {error}")
        await send_message(self.user, f"❌ **Upload Failed!**\n\n**Error:** {error}")

# --- Upload Destination Implementations ---

async def gdrive_upload(user, path, name):
    """Upload files via Google Drive"""
    from .database.pg_impl import user_set_db
    from .uploader_utils.gdrive.upload import GoogleDriveUpload

    user_id = user['user_id']
    _, token_blob = user_set_db.get_user_setting(user_id, 'gdrive_token')

    if not token_blob:
        await send_message(user, "❌ **GDrive token not found!**\nPlease upload your `token.pickle` file in Uploader Settings.")
        return

    listener = UploaderListener(user, path, name)

    user_temp_path = os.path.join(Config.LOCAL_STORAGE, str(user_id), "gdrive_creds")
    os.makedirs(user_temp_path, exist_ok=True)
    token_file_path = os.path.join(user_temp_path, "token.pickle")

    with open(token_file_path, 'wb') as f:
        f.write(token_blob)

    try:
        uploader = GoogleDriveUpload(listener, path, token_path=token_file_path)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, uploader.upload)
    finally:
        shutil.rmtree(user_temp_path, ignore_errors=True)

async def rclone_upload(user, path, name):
    """Upload files via Rclone using the advanced uploader."""
    from .database.pg_impl import user_set_db
    from .uploader_utils.rclone.transfer import RcloneTransferHelper

    user_id = user['user_id']
    _, rclone_blob = user_set_db.get_user_setting(user_id, 'rclone_config')

    if not rclone_blob:
        await send_message(user, "❌ **Rclone config not found!**\nPlease upload your `rclone.conf` file in Uploader Settings.")
        return

    user_temp_path = os.path.join(Config.LOCAL_STORAGE, str(user_id), "rclone_creds")
    os.makedirs(user_temp_path, exist_ok=True)
    rclone_conf_path = os.path.join(user_temp_path, "rclone.conf")

    with open(rclone_conf_path, 'wb') as f:
        f.write(rclone_blob)

    rclone_dest, _ = user_set_db.get_user_setting(user_id, 'rclone_dest')
    if not rclone_dest:
        rclone_dest = Config.RCLONE_PATH

    if not rclone_dest:
        await send_message(user, "❌ **Rclone destination not set!**\nPlease set a default Rclone path in the bot's config or user settings.")
        return

    listener = UploaderListener(user, path, name)
    listener.up_dest = rclone_dest

    try:
        uploader = RcloneTransferHelper(listener, config_path=rclone_conf_path)
        await uploader.upload(path)

        # After a successful upload, construct remote_info and send the manage button
        if not listener.is_cancelled:
            remote_name = rclone_dest.split(':')[0]
            remote_path = os.path.join(rclone_dest.split(':', 1)[1], name)
            is_directory = os.path.isdir(path)

            remote_info = {
                'remote': remote_name,
                'path': remote_path,
                'is_dir': is_directory
            }
            await _post_rclone_manage_button(user, remote_info)

    finally:
        shutil.rmtree(user_temp_path, ignore_errors=True)

async def _telegram_upload(user, metadata, content_type, index=None, total=None):
    """Helper function to handle all Telegram uploads."""
    reporter = user.get('progress')
    if reporter:
        await reporter.set_stage("Uploading")
    
    if content_type == "track":
        await send_message(
            user,
            metadata['filepath'],
            'audio',
            caption=await format_string("🎵 **{title}**\n👤 {artist}\n🎧 {provider}", metadata),
            meta=metadata,
            progress_reporter=reporter,
            progress_label="Uploading",
            file_index=index,
            total_files=total,
            cancel_event=user.get('cancel_event')
        )
    elif content_type == "video":
        send_type = 'doc' if getattr(bot_set, 'video_as_document', False) else 'video'
        await send_message(
            user,
            metadata['filepath'],
            send_type,
            caption=await format_string("🎬 **{title}**\n👤 {artist}\n🎧 {provider} Music Video", metadata),
            meta=metadata,
            progress_reporter=reporter,
            progress_label="Uploading",
            file_index=1,
            total_files=1,
            cancel_event=user.get('cancel_event')
        )
    elif content_type in ["album", "playlist", "artist"]:
        # ZIP logic for albums, playlists, and artists
        use_zip = False
        if content_type == "album":
            use_zip = bool(getattr(bot_set, 'apple_album_zip', False))
            caption_template = "💿 **{title}**\n👤 {artist}\n🎧 {provider}"
        elif content_type == "playlist":
            use_zip = bool(getattr(bot_set, 'apple_playlist_zip', False))
            caption_template = "🎵 **{title}**\n👤 Curated by {artist}\n🎧 {provider} Playlist"
        elif content_type == "artist":
            use_zip = bool(getattr(bot_set, 'artist_zip', False))
            caption_template = "🎤 **{artist}**\n🎧 {provider} Discography"

        if use_zip:
            total_size = await _get_folder_size(metadata['folderpath'])
            zip_paths = []
            if total_size > MAX_SIZE:
                z = await zip_handler(metadata['folderpath'])
                zip_paths = z if isinstance(z, list) else [z]
            else:
                zip_path = await create_apple_zip(metadata['folderpath'], user['user_id'], metadata, progress=reporter, cancel_event=user.get('cancel_event'))
                zip_paths = [zip_path]
            
            caption = await format_string(caption_template, metadata)
            total_parts = len(zip_paths)
            for idx, zp in enumerate(zip_paths, start=1):
                await send_message(user, zp, 'doc', caption=caption, progress_reporter=reporter, progress_label="Uploading", file_index=idx, total_files=total_parts)
                try:
                    await asyncio.to_thread(os.remove, zp)
                except Exception as e:
                    LOGGER.error(f"Error during zip cleanup for {content_type} {metadata.get('title')}: {e}")
        else:
            # Upload tracks individually
            tracks = metadata.get('tracks') or metadata.get('items', [])
            total_tracks = len(tracks)
            for idx, track in enumerate(tracks, start=1):
                await _telegram_upload(user, track, "track", index=idx, total=total_tracks)

# --- Upload Router ---

async def upload_item(user, metadata, content_type, index=None, total=None):
    """
    Routes the upload to the correct destination based on user settings.
    """
    from .database.pg_impl import user_set_db
    user_id = user['user_id']
    
    # Get user's preferred uploader
    uploader, _ = user_set_db.get_user_setting(user_id, 'default_uploader')
    uploader = uploader or 'telegram' # Default to telegram

    path = metadata.get('filepath') or metadata.get('folderpath')
    name = metadata.get('title')

    if uploader == 'gdrive':
        await gdrive_upload(user, path, name)
    elif uploader == 'rclone':
        await rclone_upload(user, path, name)
    else: # Default to Telegram
        await _telegram_upload(user, metadata, content_type, index, total)

    # Cleanup should be handled by the final uploader function
    if uploader != 'telegram':
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
                if metadata.get('thumbnail'):
                    os.remove(metadata['thumbnail'])
            except:
                pass


# --- Original Upload Functions (Refactored) ---

async def track_upload(metadata, user, index: int = None, total: int = None):
    await upload_item(user, metadata, "track", index, total)

async def music_video_upload(metadata, user):
    await upload_item(user, metadata, "video")

async def album_upload(metadata, user):
    await upload_item(user, metadata, "album")

async def artist_upload(metadata, user):
    await upload_item(user, metadata, "artist")

async def playlist_upload(metadata, user):
    await upload_item(user, metadata, "playlist")

# --- Helpers ---

async def _get_folder_size(folder_path: str) -> int:
    total_size = 0
    for root, _, files in os.walk(folder_path):
        for f in files:
            try:
                file_path = os.path.join(root, f)
                total_size += await asyncio.to_thread(os.path.getsize, file_path)
            except Exception:
                continue
    return total_size

async def _post_rclone_manage_button(user, remote_info: dict):
    try:
        from .database.pg_impl import rclone_sessions_db
        import uuid

        # Generate a unique token for the session
        token = uuid.uuid4().hex[:10]

        # Prepare the context to be stored in the database
        src_remote = remote_info.get('remote')
        rel_path = remote_info.get('path') or ''
        is_dir = bool(remote_info.get('is_dir'))

        if is_dir:
            src_path = rel_path
            src_file = None
        else:
            src_path = os.path.dirname(rel_path)
            src_file = rel_path

        context = {
            'src_remote': src_remote,
            'base': remote_info.get('base') if isinstance(remote_info, dict) else None,
            'src_path': src_path,
            'src_file': src_file,
            'dst_remote': None,
            'dst_path': '',
            'cc_mode': 'copy',
            'src_page': 0
        }

        # Save the session to the database
        rclone_sessions_db.add_session(
            token=token,
            user_id=user['user_id'],
            context=context
        )

        # Button to open manage UI, with the token in the callback
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 Browse uploaded (Copy/Move)", callback_data=f"rcloneManageStart|{token}")]
        ])
        await send_message(user, "Manage the uploaded item:", markup=kb)
    except Exception as e:
        try:
            LOGGER.error(f"Failed to create rclone manage button: {e}", exc_info=True)
            await send_message(user, "Note: manage button unavailable.")
        except Exception:
            pass
