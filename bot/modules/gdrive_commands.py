import asyncio
import time
from secrets import token_urlsafe

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .. import bot_loop, task_dict, task_dict_lock
from ..helpers.database.pg_impl import user_set_db
from ..helpers.message import send_message, edit_message, delete_message
from ..helpers.uploader_utils.ext.bot_utils import sync_to_async
from ..helpers.uploader_utils.ext.links_utils import is_gdrive_link
from ..helpers.uploader_utils.gdrive.clone import GoogleDriveClone
from ..helpers.uploader_utils.gdrive.count import GoogleDriveCount
from ..helpers.uploader_utils.gdrive.delete import GoogleDriveDelete
from ..helpers.uploader_utils.gdrive.search import GoogleDriveSearch
from ..helpers.listeners.task_listener import TaskListener
from ..helpers.status import GDriveStatus, MirrorStatus
from ..helpers.utils import get_readable_file_size, get_readable_time
from config import Config

# This listener will be created per-task
class GDriveCloneListener(TaskListener):
    def __init__(self, message: Message, client: Client, is_clone=False):
        super().__init__(message, client, is_clone)

    async def on_clone_complete(self, link, files, folders, mime_type, dir_id):
        msg = (
            f"✅ **Clone Complete!**\n\n"
            f"**Name:** `{self.name}`\n"
            f"**Size:** {get_readable_file_size(self.size)}\n\n"
            f"**Link:** {link}"
        )
        await edit_message(self.message, msg)
        async with task_dict_lock:
            if self.uid in task_dict:
                del task_dict[self.uid]

    async def on_upload_error(self, error): # Renamed back to on_upload_error
        msg = f"❌ **Clone Failed!**\n\n**Error:** {error}"
        self.is_cancelled = True
        await edit_message(self.message, msg)
        async with task_dict_lock:
            if self.uid in task_dict:
                del task_dict[self.uid]

async def _clone_task_worker(listener: GDriveCloneListener):
    """The core worker for the clone task."""
    try:
        counter = GoogleDriveCount()
        name, mime_type, size, files, folders = await sync_to_async(counter.count, listener.link, listener.user_id)

        if mime_type is None:
            await listener.on_upload_error(name)
            return

        listener.name = name
        listener.size = size

        drive = GoogleDriveClone(listener)
        gid = token_urlsafe(12)

        async with task_dict_lock:
            task_dict[listener.uid] = GDriveStatus(listener, drive, gid, "cl")

        flink, mime_type, files, folders, dir_id = await sync_to_async(drive.clone)

        if listener.is_cancelled:
            return

        if flink:
            await listener.on_clone_complete(flink, files, folders, mime_type, dir_id)
        else:
            if not listener.is_cancelled:
                await listener.on_upload_error("Unknown error occurred during clone.")

    except Exception as e:
        await listener.on_upload_error(str(e))

async def _status_updater():
    """Periodically updates all status messages."""
    while True:
        async with task_dict_lock:
            if not task_dict:
                await asyncio.sleep(1)
                continue

            for listener_id, status in list(task_dict.items()):
                listener = status.listener
                if listener.is_cancelled:
                    del task_dict[listener_id]
                    continue

                if (time.time() - listener.last_edit_time) > 3:
                    try:
                        text = (
                            f"**Status:** `{status.status()}`\n"
                            f"**Name:** `{status.name()}`\n"
                            f"**Size:** `{status.size()}`\n"
                            f"**Progress:** `{status.progress()}`\n"
                            f"**Speed:** `{status.speed()}` | **ETA:** `{status.eta()}`"
                        )
                        await edit_message(listener.message, text)
                        listener.last_edit_time = time.time()
                    except:
                        listener.is_cancelled = True
                        del task_dict[listener_id]
        await asyncio.sleep(1)

@Client.on_message(filters.command("clone"))
async def clone_command(client: Client, message: Message):
    if " " in message.text:
        link = message.text.split(" ", 1)[1]
    elif reply_to := message.reply_to_message:
        link = reply_to.text.strip()
    else:
        await send_message(message, "Please provide a GDrive link to clone.")
        return

    if not is_gdrive_link(link):
        await send_message(message, "That's not a valid GDrive link.")
        return

    listener = GDriveCloneListener(message, client, is_clone=True)
    listener.link = link

    status_msg = await send_message(message, f"Cloning: `{listener.link}`\nThis message will be updated with the status.")
    listener.message = status_msg
    listener.uid = status_msg.id

    bot_loop.create_task(_clone_task_worker(listener))

@Client.on_message(filters.command("count"))
async def count_command(client: Client, message: Message):
    if " " in message.text:
        link = message.text.split(" ", 1)[1]
    elif reply_to := message.reply_to_message:
        link = reply_to.text.strip()
    else:
        await send_message(message, "Please provide a GDrive link to count.")
        return

    if not is_gdrive_link(link):
        await send_message(message, "That's not a valid GDrive link.")
        return

    status_msg = await send_message(message, f"Counting: `{link}`")

    counter = GoogleDriveCount()
    name, mime_type, size, files, folders = await sync_to_async(counter.count, link, message.from_user.id)

    if mime_type is None:
        await edit_message(status_msg, f"❌ **Error:** {name}")
    else:
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
    if " " in message.text:
        link = message.text.split(" ", 1)[1]
    elif reply_to := message.reply_to_message:
        link = reply_to.text.strip()
    else:
        await send_message(message, "Please provide a GDrive link to delete.")
        return

    if not is_gdrive_link(link):
        await send_message(message, "That's not a valid GDrive link.")
        return

    status_msg = await send_message(message, f"Deleting: `{link}`")

    deleter = GoogleDriveDelete()
    result = await sync_to_async(deleter.deletefile, link, message.from_user.id)

    await edit_message(status_msg, result)

@Client.on_message(filters.command("gsearch"))
async def gdrive_search_command(client: Client, message: Message):
    if len(message.text.split()) == 1:
        await send_message(message, "Please provide a search keyword.")
        return

    user_id = message.from_user.id

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Folders", callback_data=f"gsearch_folders_{user_id}"),
                InlineKeyboardButton("Files", callback_data=f"gsearch_files_{user_id}"),
                InlineKeyboardButton("Both", callback_data=f"gsearch_both_{user_id}")
            ],
            [
                InlineKeyboardButton("Cancel", callback_data=f"gsearch_cancel_{user_id}")
            ]
        ]
    )
    await send_message(message, "Choose what to search for:", reply_markup=buttons)


@Client.on_callback_query(filters.regex("^gsearch_"))
async def gdrive_search_callback(client: Client, callback_query):
    user_id = callback_query.from_user.id
    message = callback_query.message
    data = callback_query.data.split("_")

    if int(data[2]) != user_id:
        await callback_query.answer("This is not for you.", show_alert=True)
        return

    if data[1] == "cancel":
        await callback_query.answer("Search canceled.")
        await message.delete()
        return

    search_type = data[1]

    try:
        search_key = message.reply_to_message.text.split(" ", 1)[1]
    except (AttributeError, IndexError):
        await message.edit("Something went wrong. Please try the search command again.")
        return

    await message.edit(f"Searching for '{search_key}' in {search_type}...")

    gdrive_id, _ = await user_set_db.get_user_setting(user_id, 'gdrive_id')
    if not gdrive_id:
        gdrive_id = Config.GDRIVE_ID or "root"

    searcher = GoogleDriveSearch(item_type=search_type)

    results, total_count = await sync_to_async(searcher.drive_list, search_key, gdrive_id, user_id)

    if not results:
        await message.edit(f"No results found for '{search_key}'.")
        return

    output = f"**Search Results for '{search_key}'** ({total_count} found):\n\n"
    output += "\n".join(results[:20])
    if total_count > 20:
        output += f"\n\n...and {total_count - 20} more."

    await message.edit(output)

# Add the status updater to the main event loop
bot_loop.create_task(_status_updater())
