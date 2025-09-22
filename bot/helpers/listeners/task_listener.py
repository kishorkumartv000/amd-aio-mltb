class TaskListener:
    def __init__(self, message, client, is_clone=False):
        self.message = message
        self.client = client
        self.uid = message.id
        self.last_edit_time = 0
        self.is_cancelled = False
        self.name = ""
        self.size = 0
        self.link = ""
        self.up_dest = ""
        self.user_id = message.from_user.id
        self.mid = message.id
        self.is_clone = is_clone
        self.excluded_extensions = []

    async def on_clone_complete(self, link, files, folders, mime_type, dir_id):
        # This will be implemented in the command module
        pass

    async def on_clone_error(self, error):
        # This will be implemented in the command module
        pass
