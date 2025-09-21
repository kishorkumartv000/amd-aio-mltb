# bot/helpers/database/mongodb_backend.py

from .interface import (
    AbstractSettingsRepo,
    AbstractHistoryRepo,
    AbstractUserSettingsRepo,
    AbstractRcloneSessionsRepo,
    DatabaseInterface
)
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
import datetime
from typing import Any, Dict, List, Optional, Tuple

class MongoSettingsRepo(AbstractSettingsRepo):
    def __init__(self, db_client: MongoClient, db_name: str):
        self._collection: Collection = db_client[db_name]["bot_settings"]
        self._collection.create_index("var_name", unique=True)

    def set_variable(self, var_name: str, var_value: Any, update_blob: bool = False, blob_val: Optional[bytes] = None) -> None:
        vtype = "str"
        if isinstance(var_value, bool):
            vtype = "bool"
        elif isinstance(var_value, int):
            vtype = "int"
        if update_blob:
            vtype = "blob"

        doc = {
            "var_name": var_name,
            "var_value": blob_val if update_blob else var_value,
            "vtype": vtype,
            "date_changed": datetime.datetime.now(datetime.timezone.utc)
        }
        self._collection.update_one({"var_name": var_name}, {"$set": doc}, upsert=True)

    def get_variable(self, var_name: str) -> Tuple[Optional[Any], Optional[bytes]]:
        doc = self._collection.find_one({"var_name": var_name})
        if not doc:
            return None, None

        val = doc.get("var_value")
        vtype = doc.get("vtype")
        blob_val = None

        if vtype == "blob":
            blob_val = val
            val = None # Main value is the blob

        return val, blob_val

class MongoHistoryRepo(AbstractHistoryRepo):
    def __init__(self, db_client: MongoClient, db_name: str):
        self._collection: Collection = db_client[db_name]["download_history"]
        self._collection.create_index([("user_id", ASCENDING), ("download_time", -1)])

    def record_download(self, user_id: int, provider: str, content_type: str, content_id: str, title: str, artist: str, quality: str) -> None:
        doc = {
            "user_id": user_id,
            "provider": provider,
            "content_type": content_type,
            "content_id": content_id,
            "title": title,
            "artist": artist,
            "quality": quality,
            "download_time": datetime.datetime.now(datetime.timezone.utc)
        }
        self._collection.insert_one(doc)

    def get_user_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        cursor = self._collection.find({"user_id": user_id}).sort("download_time", -1).limit(limit)
        return list(cursor)

class MongoUserSettingsRepo(AbstractUserSettingsRepo):
    def __init__(self, db_client: MongoClient, db_name: str):
        self._collection: Collection = db_client[db_name]["user_settings"]
        self._collection.create_index([("user_id", ASCENDING), ("setting_name", ASCENDING)], unique=True)

    def set_user_setting(self, user_id: int, setting_name: str, setting_value: Any, is_blob: bool = False) -> None:
        query = {"user_id": user_id, "setting_name": setting_name}
        update = {
            "$set": {
                "setting_value": setting_value,
                "is_blob": is_blob
            }
        }
        self._collection.update_one(query, update, upsert=True)

    def get_user_setting(self, user_id: int, setting_name: str) -> Tuple[Optional[Any], Optional[bytes]]:
        doc = self._collection.find_one({"user_id": user_id, "setting_name": setting_name})
        if not doc:
            return None, None

        is_blob = doc.get("is_blob", False)
        if is_blob:
            return None, doc.get("setting_value")
        else:
            return doc.get("setting_value"), None

class MongoRcloneSessionsRepo(AbstractRcloneSessionsRepo):
    def __init__(self, db_client: MongoClient, db_name: str):
        self._collection: Collection = db_client[db_name]["rclone_sessions"]
        self._collection.create_index("created_at", expireAfterSeconds=259200) # 3 days TTL

    def add_session(self, token: str, user_id: int, context: Dict[str, Any]) -> None:
        doc = {
            "_id": token, # Use token as the primary key
            "user_id": user_id,
            "context": context,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        self._collection.insert_one(doc)

    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        doc = self._collection.find_one({"_id": token})
        return doc.get("context") if doc else None

    def delete_session(self, token: str) -> None:
        self._collection.delete_one({"_id": token})

# --- Main Backend Class ---

class MongoDatabase(DatabaseInterface):
    """MongoDB implementation of the database interface."""

    def __init__(self):
        super().__init__()
        self._client: Optional[MongoClient] = None
        self._db_name: Optional[str] = None

    def connect(self, db_url: str, **kwargs) -> None:
        """Connect to the database and initialize repositories."""
        from config import Config
        from pymongo.errors import ConfigurationError

        if self._client:
            return

        self._client = MongoClient(db_url)

        # Determine the database name
        db_name = Config.MONGODB_DATABASE
        if not db_name:
            try:
                db_name = self._client.get_database().name
            except ConfigurationError:
                raise ConfigurationError(
                    "No default database is defined in your MongoDB URL. "
                    "Please specify one in the URL (e.g., 'mongodb://.../your_db') "
                    "or set the MONGODB_DATABASE environment variable."
                )

        self._db_name = db_name

        self.settings = MongoSettingsRepo(self._client, self._db_name)
        self.history = MongoHistoryRepo(self._client, self._db_name)
        self.user_settings = MongoUserSettingsRepo(self._client, self._db_name)
        self.rclone_sessions = MongoRcloneSessionsRepo(self._client, self._db_name)

    def disconnect(self) -> None:
        """Disconnect from the database."""
        if self._client:
            self._client.close()
            self._client = None
