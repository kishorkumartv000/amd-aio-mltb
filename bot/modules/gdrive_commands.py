from pyrogram import Client, filters
from pyrogram.types import Message

# from bot import CMD # CMD is not defined yet
from ..helpers.uploader_utils.gdrive.clone import GoogleDriveClone
from ..helpers.uploader_utils.gdrive.count import GoogleDriveCount
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

    args = message.text.split(" ", 1)
    if len(args) == 1:
        await send_message(message, "Please provide a Google Drive link to count.")
        return

    link = args[1]
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
