# bot/helpers/database/interface.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

class AbstractSettingsRepo(ABC):
    """Abstract repository for global bot settings."""

    @abstractmethod
    def set_variable(self, var_name: str, var_value: Any, update_blob: bool = False, blob_val: Optional[bytes] = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_variable(self, var_name: str) -> Tuple[Optional[Any], Optional[bytes]]:
        raise NotImplementedError

class AbstractHistoryRepo(ABC):
    """Abstract repository for download history."""

    @abstractmethod
    def record_download(self, user_id: int, provider: str, content_type: str, content_id: str, title: str, artist: str, quality: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_user_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        raise NotImplementedError

class AbstractUserSettingsRepo(ABC):
    """Abstract repository for per-user settings."""

    @abstractmethod
    def set_user_setting(self, user_id: int, setting_name: str, setting_value: Any, is_blob: bool = False) -> None:
        """Sets a setting for a user. Can be a simple value or a blob."""
        raise NotImplementedError

    @abstractmethod
    def get_user_setting(self, user_id: int, setting_name: str) -> Tuple[Optional[Any], Optional[bytes]]:
        """Gets a setting for a user, returning both simple value and blob if available."""
        raise NotImplementedError

class AbstractRcloneSessionsRepo(ABC):
    """Abstract repository for rclone browse sessions."""

    @abstractmethod
    def add_session(self, token: str, user_id: int, context: Dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete_session(self, token: str) -> None:
        raise NotImplementedError

class DatabaseInterface(ABC):
    """Abstract interface for the entire database backend."""

    def __init__(self):
        self.settings: AbstractSettingsRepo = None
        self.history: AbstractHistoryRepo = None
        self.user_settings: AbstractUserSettingsRepo = None
        self.rclone_sessions: AbstractRcloneSessionsRepo = None

    @abstractmethod
    def connect(self, db_url: str, **kwargs) -> None:
        """Connect to the database and initialize repositories."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the database."""
        raise NotImplementedError
