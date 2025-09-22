import os
import sys

# Get the parent directory of the current file (bot directory)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Get the project root directory (apple-music-bot)
project_root = os.path.dirname(current_dir)

# Add project root to Python path
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import Config

bot = Config.BOT_USERNAME

plugins = dict(
    root="bot/modules"
)

class CMD(object):
    START = ["start", f"start@{bot}"]
    HELP = ["help", f"help@{bot}"]
    SETTINGS = ["settings", f"settings@{bot}"]
    DOWNLOAD = ["download", f"download@{bot}"]
    BAN = ["ban", f"ban@{bot}"]
    AUTH = ["auth", f"auth@{bot}"]
    LOG = ["log", f"log@{bot}"]

cmd = CMD()
