import copy


class ConversationManager:
    def __init__(self):
        self._messages: list[dict] = []

    def add_user_message(self, text: str):
        self._messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str):
        self._messages.append({"role": "assistant", "content": text})

    def get_messages_for_api(self) -> list[dict]:
        return copy.deepcopy(self._messages)

    def clear(self):
        self._messages.clear()

    @property
    def messages(self) -> list[dict]:
        return self._messages
