from pyrogram import Client, filters
from pyrogram.types import Message
import asyncio

# from bot import CMD # CMD is not defined yet
from ..helpers.uploader_utils.gdrive.clone import GoogleDriveClone
from ..helpers.uploader_utils.gdrive.delete import GoogleDriveDelete
from ..helpers.uploader_utils.gdrive.search import GoogleDriveSearch
from ..helpers.uploader_utils.ext.links_utils import is_gdrive_link
from ..helpers.uploader_utils.gdrive.count import GoogleDriveCount
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..helpers.database.pg_impl import user_set_db
from ..helpers.message import send_message

class CloneListener:
    def __init__(self, message):
        self.message = message
        self.up_dest = "" # Will be set later
        self.link = ""
        self.is_cancelled = False
        self.user_id = message.from_user.id

    async def on_upload_error(self, error):
        await send_message(self.message, f"❌ **Clone Failed!**\n\n**Error:** {error}")

@Client.on_message(filters.command("clone"))
async def clone_command(client: Client, message: Message):
    """
    Handler for the /clone command.
    """
    from config import Config
    import asyncio

    args = message.text.split(" ", 1)
    if len(args) == 1:
        await send_message(message, "Please provide a Google Drive link to clone.")
        return

    link = args[1]
    listener = CloneListener(message)
    listener.link = link
    listener.up_dest = Config.GDRIVE_ID or "root"

    cloner = GoogleDriveClone(listener)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, cloner.clone)

    if result and all(result):
        durl, mime_type, total_files, total_folders, obj_id = result
        response = f"✅ **Clone Complete!**\n\n"
        response += f"**Name:** `{cloner.listener.name}`\n"
        response += f"**Type:** `{mime_type}`\n"
        response += f"**Size:** `{cloner.listener.size}`\n\n"
        response += f"**Link:** {durl}"
        await send_message(message, response)
    # The on_upload_error is handled by the listener

@Client.on_message(filters.command("count"))
async def count_command(client: Client, message: Message):
    """
    Handler for the /count command.
    """
    import asyncio

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

    user_id = message.from_user.id

    counter = GoogleDriveCount()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, counter.count, link, user_id)

    if isinstance(result, str):
        # It's an error message
        await send_message(message, f"❌ **Count Failed!**\n\n**Error:** {result}")
    elif result and all(result):
        name, mime_type, size, files, folders = result
        response = f"✅ **Count Complete!**\n\n"
        response += f"**Name:** `{name}`\n"
        response += f"**Type:** `{mime_type}`\n"
        response += f"**Size:** `{size}`\n"
        response += f"**Files:** `{files}`\n"
        response += f"**Folders:** `{folders}`"
        await send_message(message, response)


@Client.on_message(filters.command("gddel"))
async def gdrive_delete_command(client: Client, message: Message):
    """
    Handler for the /gddel command.
    """
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

    user_id = message.from_user.id
    deleter = GoogleDriveDelete()

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, deleter.deletefile, link, user_id)

    await send_message(message, result)


@Client.on_message(filters.command("gsearch"))
async def gdrive_search_command(client: Client, message: Message):
    """
    Handler for the /gsearch command.
    """
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
    """
    Callback handler for gsearch buttons
    """
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

    search_type = data[1] # folders, files, or both

    try:
        search_key = message.reply_to_message.text.split(" ", 1)[1]
    except (AttributeError, IndexError):
        await message.edit("Something went wrong. Please try the search command again.")
        return

    await message.edit(f"Searching for '{search_key}' in {search_type}...")

    # Get user's GDrive ID from DB. Fallback to root.
    gdrive_id, _ = user_set_db.get_user_setting(user_id, 'gdrive_id')
    if not gdrive_id:
        from config import Config
        gdrive_id = Config.GDRIVE_ID or "root"

    searcher = GoogleDriveSearch(item_type=search_type)
    loop = asyncio.get_event_loop()

    results, total_count = await loop.run_in_executor(None, searcher.drive_list, search_key, gdrive_id, user_id)

    if not results:
        await message.edit(f"No results found for '{search_key}'.")
        return

    # For simplicity, we'll just show the first 20 results
    output = f"**Search Results for '{search_key}'** ({total_count} found):\n\n"
    output += "\n".join(results[:20])
    if total_count > 20:
        output += f"\n\n...and {total_count - 20} more."

    await message.edit(output)
