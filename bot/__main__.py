import os
import sys
import subprocess
import asyncio

# Get the parent directory of the current file (bot directory)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Get the project root directory (apple-music-bot)
project_root = os.path.dirname(current_dir)

# Add project root to Python path
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import Config
from bot.logger import LOGGER
from . import bot_loop
from .tgclient import Bot

async def main():
    # Ensure download directory exists
    if not os.path.isdir(Config.LOCAL_STORAGE):
        os.makedirs(Config.LOCAL_STORAGE)
        LOGGER.info(f"Created download directory: {Config.LOCAL_STORAGE}")
    
    # Ensure Apple Music downloader is installed and executable
    downloader_path = Config.DOWNLOADER_PATH
    if not os.path.exists(downloader_path):
        LOGGER.warning("Apple Music downloader not found! Attempting installation...")
        try:
            subprocess.run([Config.INSTALLER_PATH], check=True)
            LOGGER.info("Apple Music downloader installed successfully")
        except Exception as e:
            LOGGER.error(f"Apple Music installer failed: {str(e)}")
    
    if os.path.exists(downloader_path):
        try:
            # Set execute permissions
            os.chmod(downloader_path, 0o755)
            LOGGER.info(f"Set execute permissions on: {downloader_path}")
        except Exception as e:
            LOGGER.error(f"Failed to set permissions: {str(e)}")
    
    # Create and start the bot
    LOGGER.info("Starting Apple Music Downloader Bot...")
    aio = Bot()
    await aio.start()
    LOGGER.info("Bot Started!")

    # Keep the main coroutine alive to listen for tasks
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        bot_loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Bot stopped by user")
    except Exception as e:
        LOGGER.error(f"Bot exited with an error: {e}", exc_info=True)
    finally:
        bot_loop.stop()
        LOGGER.info("Bot event loop stopped.")
