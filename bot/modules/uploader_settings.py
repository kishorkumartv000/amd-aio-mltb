import os
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import CMD
from ..helpers.database.pg_impl import user_set_db
from config import Config


async def _get_main_settings_payload(user_id: int):
    """Generates the text and buttons for the main uploader settings panel."""
    default_uploader, _ = user_set_db.get_user_setting(user_id, 'default_uploader')
    if not default_uploader:
        default_uploader = "Telegram"

    text = (f"⚙️ **Uploader Settings**\n\n"
            f"Here you can configure your upload destinations.\n\n"
            f"**Current Default Uploader:** `{default_uploader.capitalize()}`")

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬆️ Set Default Uploader", callback_data="us_set_default")],
        [
            InlineKeyboardButton("🔐 GDrive Settings", callback_data="us_gdrive"),
            InlineKeyboardButton("☁️ Rclone Settings", callback_data="us_rclone"),
        ],
        [InlineKeyboardButton("❌ Close", callback_data="us_close")]
    ])
    return text, buttons

async def _get_gdrive_settings_payload(user_id: int):
    """Generates the text and buttons for the GDrive settings panel."""
    gdrive_id, _ = user_set_db.get_user_setting(user_id, 'gdrive_id')
    index_url, _ = user_set_db.get_user_setting(user_id, 'index_url')
    stop_duplicate, _ = user_set_db.get_user_setting(user_id, 'stop_duplicate')

    # Fallback to config values if not set by the user
    gdrive_id = gdrive_id or Config.GDRIVE_ID or "Not Set"
    index_url = index_url or Config.INDEX_URL or Config.INDEX_LINK or "Not Set"
    if stop_duplicate is None:
        stop_duplicate = Config.STOP_DUPLICATE

    token_status = "Present" if os.path.exists("token.pickle") else "Not Uploaded"

    text = (f"**Google Drive Settings**\n\n"
            f"**Token Status:** `{token_status}`\n"
            f"**GDrive Folder ID:** `{gdrive_id}`\n"
            f"**Index URL:** `{index_url}`\n"
            f"**Stop Duplicate:** `{'Enabled' if stop_duplicate else 'Disabled'}`")

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️ Upload token.pickle", callback_data="us_gdrive_upload"),
            InlineKeyboardButton("✏️ Set Folder ID", callback_data="us_gdrive_set_id"),
        ],
        [
            InlineKeyboardButton("🔗 Set Index URL", callback_data="us_gdrive_set_index"),
            InlineKeyboardButton(f"Toggle Stop Duplicate", callback_data="us_gdrive_toggle_duplicate"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="us_back_main")]
    ])
    return text, buttons

async def _get_rclone_settings_payload(user_id: int):
    """Generates the text and buttons for the Rclone settings panel."""
    rclone_dest, _ = user_set_db.get_user_setting(user_id, 'rclone_dest')
    rclone_flags, _ = user_set_db.get_user_setting(user_id, 'rclone_flags')

    # Fallback to config values if not set by the user
    rclone_dest = rclone_dest or Config.RCLONE_DEST or "Not Set"
    rclone_flags = rclone_flags or Config.RCLONE_FLAGS or "Not Set"

    rclone_conf_status = "Present" if os.path.exists("rclone.conf") else "Not Uploaded"

    text = (f"**Rclone Settings**\n\n"
            f"**Config Status:** `{rclone_conf_status}`\n"
            f"**Current Destination:** `{rclone_dest}`\n"
            f"**Rclone Flags:** `{rclone_flags}`")

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️ Upload rclone.conf", callback_data="us_rclone_upload"),
            InlineKeyboardButton("✏️ Set Destination", callback_data="us_rclone_set_path"),
        ],
        [InlineKeyboardButton("🚩 Set Rclone Flags", callback_data="us_rclone_set_flags")],
        [InlineKeyboardButton("⬅️ Back", callback_data="us_back_main")]
    ])
    return text, buttons


from bot import cmd

@Client.on_message(filters.command(cmd.UPLOADERSETTINGS))
async def uploader_settings_command(client: Client, message: Message):
    """Main command to access uploader settings."""
    text, buttons = await _get_main_settings_payload(message.from_user.id)
    await message.reply_text(text, reply_markup=buttons)


@Client.on_callback_query(filters.regex("^us_"))
async def uploader_settings_callbacks(client: Client, callback_query: CallbackQuery):
    """Handle callbacks from the uploader settings panel."""
    user_id = callback_query.from_user.id
    data = callback_query.data
    message = callback_query.message

    if data == "us_close":
        await message.delete()
        return

    if data == "us_back_main":
        text, buttons = await _get_main_settings_payload(user_id)
        await message.edit_text(text, reply_markup=buttons)

    elif data == "us_set_default":
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✈️ Telegram", callback_data="us_set_default_telegram"),
                InlineKeyboardButton("🔐 Google Drive", callback_data="us_set_default_gdrive"),
                InlineKeyboardButton("☁️ Rclone", callback_data="us_set_default_rclone"),
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="us_back_main")]
        ])
        await message.edit_text("Select your default upload destination:", reply_markup=buttons)

    elif data.startswith("us_set_default_"):
        new_default = data.split("_")[-1]
        user_set_db.set_user_setting(user_id, 'default_uploader', new_default)
        await callback_query.answer(f"Default uploader set to {new_default.capitalize()}", show_alert=True)
        text, buttons = await _get_main_settings_payload(user_id)
        await message.edit_text(text, reply_markup=buttons)

    # GDrive Section
    elif data == "us_gdrive":
        text, buttons = await _get_gdrive_settings_payload(user_id)
        await message.edit_text(text, reply_markup=buttons)

    elif data == "us_gdrive_upload":
        await callback_query.answer("Please reply with your token.pickle file.", show_alert=True)
        await message.reply_text("Send your `token.pickle` file here.")

    elif data == "us_gdrive_set_id":
        await callback_query.answer("Please reply with your Google Drive Folder ID.", show_alert=True)
        await message.reply_text("Send your Google Drive Folder ID here.")

    elif data == "us_gdrive_set_index":
        await callback_query.answer("Please reply with your Index URL.", show_alert=True)
        await message.reply_text("Send your Index URL here.")

    elif data == "us_gdrive_toggle_duplicate":
        stop_duplicate, _ = user_set_db.get_user_setting(user_id, 'stop_duplicate')
        if stop_duplicate is None: stop_duplicate = True
        new_state = not stop_duplicate
        user_set_db.set_user_setting(user_id, 'stop_duplicate', new_state)
        await callback_query.answer(f"Stop Duplicate has been {'Enabled' if new_state else 'Disabled'}.", show_alert=True)
        text, buttons = await _get_gdrive_settings_payload(user_id)
        await message.edit_text(text, reply_markup=buttons)

    # Rclone Section
    elif data == "us_rclone":
        text, buttons = await _get_rclone_settings_payload(user_id)
        await message.edit_text(text, reply_markup=buttons)

    elif data == "us_rclone_upload":
        await callback_query.answer("Please reply with your rclone.conf file.", show_alert=True)
        await message.reply_text("Send your `rclone.conf` file here.")

    elif data == "us_rclone_set_path":
        await callback_query.answer("Please reply with your rclone destination path.", show_alert=True)
        await message.reply_text("Send your Rclone destination path here (e.g., `my_remote:path/to/folder`).")

    elif data == "us_rclone_set_flags":
        await callback_query.answer("Please reply with your Rclone flags.", show_alert=True)
        await message.reply_text("Send your Rclone flags here (e.g., `--drive-chunk-size 128M`).")


@Client.on_message((filters.document | filters.text) & filters.reply)
async def handle_config_uploads(client: Client, message: Message):
    """Handles the upload of config files and setting of text-based configs."""
    if not message.reply_to_message or not message.reply_to_message.text:
        return

    user_id = message.from_user.id
    reply_text = message.reply_to_message.text

    # --- File-based settings ---
    if "rclone.conf" in reply_text:
        if not message.document or message.document.file_name != 'rclone.conf':
            await message.reply_text("Please upload the file named `rclone.conf`.")
            return
        await message.download(file_name="rclone.conf")
        await message.reply_text("✅ `rclone.conf` has been saved to the working directory.")
        return # Done with this handler

    if "token.pickle" in reply_text:
        if not message.document or message.document.file_name != 'token.pickle':
            await message.reply_text("Please upload the file named `token.pickle`.")
            return
        await message.download(file_name="token.pickle")
        await message.reply_text("✅ `token.pickle` has been saved to the working directory.")
        return # Done with this handler

    # --- Database settings ---
    setting_name = ""
    setting_value = ""
    if "Google Drive Folder ID" in reply_text:
        if not message.text: return
        setting_name = "gdrive_id"
        setting_value = message.text.strip()
        success_message = f"✅ GDrive Folder ID set to `{setting_value}`."
    elif "Index URL" in reply_text:
        if not message.text: return
        setting_name = "index_url"
        setting_value = message.text.strip()
        success_message = f"✅ Index URL set to `{setting_value}`."
    elif "Rclone destination path" in reply_text:
        if not message.text: return
        setting_name = "rclone_dest"
        setting_value = message.text.strip()
        success_message = f"✅ Rclone destination set to `{setting_value}`."
    elif "Rclone flags" in reply_text:
        if not message.text: return
        setting_name = "rclone_flags"
        setting_value = message.text.strip()
        success_message = f"✅ Rclone flags set to `{setting_value}`."
    else:
        return

    if setting_name and setting_value:
        user_set_db.set_user_setting(user_id, setting_name, setting_value, is_blob=False)
        await message.reply_text(success_message)
    else:
        await message.reply_text("❌ No value received.")
