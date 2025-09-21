from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot import CMD
from ..helpers.database.pg_impl import user_set_db

@Client.on_message(filters.command(["uploadersettings", "usettings"]))
async def uploader_settings_command(client: Client, message: Message):
    """
    Main command to access uploader settings.
    """
    user_id = message.from_user.id

    # Fetch current default uploader
    default_uploader, _ = user_set_db.get_user_setting(user_id, 'default_uploader')
    if not default_uploader:
        default_uploader = "Telegram" # Default if not set

    text = f"⚙️ **Uploader Settings**\n\n"
    text += f"Here you can configure your upload destinations.\n\n"
    text += f"**Current Default Uploader:** `{default_uploader.capitalize()}`"

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬆️ Set Default Uploader", callback_data="us_set_default"),
            ],
            [
                InlineKeyboardButton("🔐 GDrive Settings", callback_data="us_gdrive"),
                InlineKeyboardButton("☁️ Rclone Settings", callback_data="us_rclone"),
            ],
            [
                InlineKeyboardButton("❌ Close", callback_data="us_close"),
            ]
        ]
    )

    await message.reply_text(text, reply_markup=buttons)

@Client.on_callback_query(filters.regex("^us_"))
async def uploader_settings_callbacks(client: Client, callback_query):
    """
    Handle callbacks from the uploader settings panel.
    """
    data = callback_query.data

    if data == "us_close":
        await callback_query.message.delete()
    elif data == "us_set_default":
        # This will show the options to change the default uploader
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✈️ Telegram", callback_data="us_set_default_telegram"),
                    InlineKeyboardButton("🔐 Google Drive", callback_data="us_set_default_gdrive"),
                    InlineKeyboardButton("☁️ Rclone", callback_data="us_set_default_rclone"),
                ],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="us_back_main"),
                ]
            ]
        )
        await callback_query.message.edit_text("Select your default upload destination:", reply_markup=buttons)

    elif data.startswith("us_set_default_"):
        user_id = callback_query.from_user.id
        new_default = data.split("_")[-1]
        user_set_db.set_user_setting(user_id, 'default_uploader', new_default)
        await callback_query.answer(f"Default uploader set to {new_default.capitalize()}", show_alert=True)
        # Refresh the main settings panel
        await uploader_settings_command(client, callback_query.message)

    elif data == "us_back_main":
        # Refresh the main settings panel by calling the original command function
        await uploader_settings_command(client, callback_query.message)

    elif data == "us_gdrive":
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("⬆️ Upload token.pickle", callback_data="us_gdrive_upload"),
                ],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="us_back_main"),
                ]
            ]
        )
        await callback_query.message.edit_text("GDrive Settings:", reply_markup=buttons)

    elif data == "us_gdrive_upload":
        await callback_query.answer("Please reply to my next message with your token.pickle file.", show_alert=True)
        await callback_query.message.reply_text("Send your `token.pickle` file here. This message will be used to identify your reply.")

    elif data == "us_rclone":
        # Get current rclone dest
        rclone_dest, _ = user_set_db.get_user_setting(callback_query.from_user.id, 'rclone_dest')
        if not rclone_dest:
            from config import Config
            rclone_dest = Config.RCLONE_PATH or "Not Set"

        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("⬆️ Upload rclone.conf", callback_data="us_rclone_upload"),
                    InlineKeyboardButton("✏️ Set Destination", callback_data="us_rclone_set_path"),
                ],
                [
                    InlineKeyboardButton("⬅️ Back", callback_data="us_back_main"),
                ]
            ]
        )
        await callback_query.message.edit_text(f"**Rclone Settings**\n\n**Current Destination:** `{rclone_dest}`", reply_markup=buttons)

    elif data == "us_rclone_upload":
        await callback_query.answer("Please reply to my next message with your rclone.conf file.", show_alert=True)
        await callback_query.message.reply_text("Send your `rclone.conf` file here. This message will be used to identify your reply.")

    elif data == "us_rclone_set_path":
        await callback_query.answer("Please reply to my next message with your rclone destination path.", show_alert=True)
        await callback_query.message.reply_text("Send your Rclone destination path here (e.g., `my_remote:path/to/folder`). This message will be used to identify your reply.")

    else:
        await callback_query.answer("Not implemented yet.", show_alert=True)

@Client.on_message((filters.document | filters.text) & filters.reply)
async def handle_config_uploads(client: Client, message: Message):
    """
    Handles the upload of config files and setting of text-based configs.
    """
    if not message.reply_to_message or not message.reply_to_message.text:
        return

    user_id = message.from_user.id
    reply_text = message.reply_to_message.text
    is_blob = False

    if "rclone.conf" in reply_text:
        if not message.document: return
        setting_name = "rclone_config"
        setting_value = (await message.download(in_memory=True)).read()
        is_blob = True
        success_message = "✅ `rclone.conf` has been saved successfully."
    elif "token.pickle" in reply_text:
        if not message.document: return
        setting_name = "gdrive_token"
        setting_value = (await message.download(in_memory=True)).read()
        is_blob = True
        success_message = "✅ `token.pickle` has been saved successfully."
    elif "Rclone destination path" in reply_text:
        if not message.text: return
        setting_name = "rclone_dest"
        setting_value = message.text.strip()
        success_message = f"✅ Rclone destination set to `{setting_value}`."
    else:
        return

    user_set_db.set_user_setting(user_id, setting_name, setting_value, is_blob=is_blob)

    await message.reply_text(success_message)
