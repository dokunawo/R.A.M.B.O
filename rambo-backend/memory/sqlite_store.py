class SQLiteStore:
    def __init__(self):
        # Placeholder store — expand later
        self.db = {}

    def save(self, key, value):
        self.db[key] = value

    def get(self, key):
        return self.db.get(key)
