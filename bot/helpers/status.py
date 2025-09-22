from ..helpers.utils import get_readable_file_size, get_readable_time

class MirrorStatus:
    STATUS_CLONE = "Cloning"
    STATUS_DOWNLOAD = "Downloading"
    STATUS_UPLOAD = "Uploading"
    STATUS_QUEUEDL = "QueueDl"
    STATUS_QUEUEUP = "QueueUp"
    STATUS_PAUSED = "Pause"
    STATUS_ARCHIVE = "Archive"
    STATUS_EXTRACT = "Extract"
    STATUS_SPLIT = "Split"
    STATUS_CHECK = "CheckUp"
    STATUS_SEED = "Seed"

class GDriveStatus:
    def __init__(self, listener, obj, gid, status):
        self.listener = listener
        self._obj = obj
        self._gid = gid
        self._status = status
        self.tool = "gDriveApi"

    def processed_bytes(self):
        return self._obj.processed_bytes

    def size(self):
        return get_readable_file_size(self.listener.size)

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
            return (self._obj.processed_bytes / self.listener.size) * 100
        except ZeroDivisionError:
            return 0

    def progress(self):
        return f"{round(self.progress_raw(), 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed)}/s"

    def eta(self):
        try:
            seconds = (self.listener.size - self._obj.processed_bytes) / self._obj.speed
            return get_readable_time(seconds)
        except ZeroDivisionError:
            return "-"
        except:
            return "-"

    def task(self):
        return self._obj
