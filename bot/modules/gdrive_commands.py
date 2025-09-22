import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from secrets import token_urlsafe
from ..helpers.database.pg_impl import user_set_db

from ..helpers.uploader_utils.gdrive.clone import GoogleDriveClone
from ..helpers.uploader_utils.gdrive.count import GoogleDriveCount
from ..helpers.uploader_utils.gdrive.delete import GoogleDriveDelete
from ..helpers.uploader_utils.gdrive.search import GoogleDriveSearch
from ..helpers.uploader_utils.ext.links_utils import is_gdrive_link
from ..helpers.message import send_message, edit_message, delete_message
from ..helpers.utils import get_readable_file_size, get_readable_time
from config import Config

# --- Globals for Task Management ---
task_dict = {}
task_dict_lock = asyncio.Lock()
# ------------------------------------

class MirrorStatus:
    STATUS_CLONE = "Cloning"
    STATUS_DOWNLOAD = "Downloading"
    STATUS_UPLOAD = "Uploading"

class GoogleDriveStatus:
    def __init__(self, listener, obj, gid, status):
        self.listener = listener
        self._obj = obj
        self._size = self.listener.size
        self._gid = gid
        self._status = status
        self.tool = "gDriveApi"

    def processed_bytes(self):
        return self._obj.processed_bytes

    def size(self):
        return get_readable_file_size(self._size)

    def status(self):
        if self._status == "up":
            return MirrorStatus.STATUS_UPLOAD
        elif self._status == "dl":
            return MirrorStatus.STATUS_DOWNLOAD
        else:
            return MirrorStatus.STATUS_CLONE

    def name(self):
        return self.listener.name

    def gid(self) -> str:
        return self._gid

    def progress_raw(self):
        try:
            return self._obj.processed_bytes / self._size * 100
        except:
            return 0

    def progress(self):
        return f"{round(self.progress_raw(), 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed)}/s"

    def eta(self):
        try:
            seconds = (self._size - self._obj.processed_bytes) / self._obj.speed
            return get_readable_time(seconds)
        except:
            return "-"

    def task(self):
        return self._obj

class CloneListener:
    def __init__(self, message: Message, name="", up_dest="", link=""):
        self.message = message
        self.name = name
        self.up_dest = up_dest
        self.link = link
        self.size = 0
        self.is_cancelled = False
        self.is_clone = True
        self.user_id = message.from_user.id
        self.mid = message.id
        self.excluded_extensions = [] # Fix for the crash

    async def on_clone_complete(self, link, files, folders, mime_type, dir_id):
        msg = (
            f"✅ **Clone Complete!**\n\n"
            f"**Name:** `{self.name}`\n"
            f"**Size:** {get_readable_file_size(self.size)}\n"
            f"**Type:** `{mime_type}`\n"
            f"**Files:** `{files}`\n"
            f"**Folders:** `{folders}`\n\n"
            f"**Link:** {link}"
        )
        async with task_dict_lock:
            if self.mid in task_dict:
                del task_dict[self.mid]
        await edit_message(self.message, msg)


    async def on_upload_error(self, error):
        msg = f"❌ **Clone Failed!**\n\n**Error:** {error}"
        self.is_cancelled = True
        async with task_dict_lock:
            if self.mid in task_dict:
                del task_dict[self.mid]
        await edit_message(self.message, msg)

async def send_status_message(message: Message):
    async with task_dict_lock:
        if message.id not in task_dict:
            return
        status = task_dict[message.id]

    while not status.task().is_cancelled:
        # Update name and size in case they were updated after count
        status.listener.name = status.task().listener.name
        status._size = status.task().listener.size

        progress = status.progress()
        speed = status.speed()
        eta = status.eta()
        text = (
            f"**Status:** `{status.status()}`\n"
            f"**Name:** `{status.name()}`\n"
            f"**Size:** `{status.size()}`\n"
            f"**Progress:** `{progress}`\n"
            f"**Speed:** `{speed}` | **ETA:** `{eta}`"
        )
        try:
            await edit_message(message, text)
            await asyncio.sleep(3)
        except: # Message deleted
            status.task().is_cancelled = True
            return

@Client.on_message(filters.command("clone"))
async def clone_command(client: Client, message: Message):
    args = message.text.split()
    if len(args) == 1 and not message.reply_to_message:
        await send_message(message, "Provide a GDrive link to clone.")
        return

    link = args[1] if len(args) > 1 else message.reply_to_message.text

    if not is_gdrive_link(link):
        await send_message(message, "Please provide a valid Google Drive link.")
        return

    gdrive_id, _ = await user_set_db.get_user_setting(message.from_user.id, 'gdrive_id')
    up_dest = gdrive_id or Config.GDRIVE_ID or "root"

    status_msg = await send_message(message, "Preparing to clone, please wait...")

    listener = CloneListener(status_msg, link=link, up_dest=up_dest)

    counter = GoogleDriveCount()
    name, mime_type, size, files, _ = await asyncio.get_event_loop().run_in_executor(None, counter.count, link, listener.user_id)

    if mime_type is None:
        await edit_message(status_msg, f"❌ **Error:** {name}")
        return

    listener.name = name
    listener.size = size

    cloner = GoogleDriveClone(listener)
    gid = token_urlsafe(12)

    async with task_dict_lock:
        task_dict[status_msg.id] = GoogleDriveStatus(listener, cloner, gid, "cl")

    clone_task = asyncio.create_task(asyncio.get_event_loop().run_in_executor(None, cloner.clone))
    status_task = asyncio.create_task(send_status_message(status_msg))

    result = await clone_task
    status_task.cancel()

    if listener.is_cancelled:
        return

    if result and all(r is not None for r in result):
        durl, res_mime_type, total_files, total_folders, obj_id = result
        await listener.on_clone_complete(durl, total_files, total_folders, res_mime_type, obj_id)
    # Errors are handled by on_upload_error called from the helper

@Client.on_message(filters.command("count"))
async def count_command(client: Client, message: Message):
    args = message.text.split()
    if len(args) > 1:
        link = args[1]
    elif reply_to := message.reply_to_message:
        link = reply_to.text.split(maxsplit=1)[0].strip()
    else:
        link = ""

    if not is_gdrive_link(link):
        await send_message(message, "Please provide a valid Google Drive link to count.")
        return

    status_msg = await send_message(message, f"Counting: `{link}`")

    counter = GoogleDriveCount()
    result = await asyncio.get_event_loop().run_in_executor(None, counter.count, link, message.from_user.id)

    if not isinstance(result, tuple) or not all(r is not None for r in result):
        await edit_message(status_msg, f"❌ **Count Failed!**\n\n**Error:** {result or 'Unknown error'}")
        return

    name, mime_type, size, files, folders = result
    response = (
        f"✅ **Count Complete!**\n\n"
        f"**Name:** `{name}`\n"
        f"**Type:** `{mime_type}`\n"
        f"**Size:** `{get_readable_file_size(size)}`\n"
        f"**Files:** `{files}`\n"
        f"**Folders:** `{folders}`"
    )
    await edit_message(status_msg, response)

@Client.on_message(filters.command("gddel"))
async def gdrive_delete_command(client: Client, message: Message):
    args = message.text.split()
    if len(args) > 1:
        link = args[1]
    elif reply_to := message.reply_to_message:
        link = reply_to.text.split(maxsplit=1)[0].strip()
    else:
        link = ""

    if not is_gdrive_link(link):
        await send_message(message, "Please provide a valid Google Drive link to delete.")
        return

    status_msg = await send_message(message, f"Deleting: `{link}`")

    deleter = GoogleDriveDelete()
    result = await asyncio.get_event_loop().run_in_executor(None, deleter.deletefile, link, message.from_user.id)

    await edit_message(status_msg, result)

@Client.on_message(filters.command("gsearch"))
async def gdrive_search_command(client: Client, message: Message):
    await send_message(message, "This command is not fully implemented yet.")

@Client.on_callback_query(filters.regex("^gsearch_"))
async def gdrive_search_callback(client: Client, callback_query):
    await callback_query.answer("This command is not fully implemented yet.", show_alert=True)
