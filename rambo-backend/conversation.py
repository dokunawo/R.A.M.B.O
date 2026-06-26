import asyncio
import copy

# Keep the in-memory prompt prefix bounded — older turns still live in the
# conversation repo (and Keeper), but we don't resend an ever-growing history to
# the model. _cache_last_message handles the rolling cache breakpoint.
_MAX_IN_MEMORY = 40


class ConversationManager:
    def __init__(self):
        self._messages: list[dict] = []
        self._repo = None  # optional ConversationRepo, wired at startup

    def set_repo(self, repo) -> None:
        self._repo = repo

    async def hydrate(self, limit: int = 20) -> None:
        """Load recent turns from the repo so context survives restarts."""
        if not self._repo:
            return
        try:
            rows = await self._repo.recent(limit)
            self._messages = [{"role": r["role"], "content": r["content"]} for r in rows]
        except Exception:
            pass  # best-effort — start fresh if the repo can't be read

    def _persist(self, role: str, text: str) -> None:
        """Fire-and-forget durable write (never blocks/raises into the voice path)."""
        if not self._repo:
            return
        try:
            asyncio.get_running_loop().create_task(self._repo.append(role, text))
        except RuntimeError:
            pass  # no running loop (e.g. unit test calling sync path) — skip

    def _trim(self) -> None:
        if len(self._messages) > _MAX_IN_MEMORY:
            self._messages = self._messages[-_MAX_IN_MEMORY:]

    def add_user_message(self, text: str):
        self._messages.append({"role": "user", "content": text})
        self._persist("user", text)
        self._trim()

    def add_assistant_message(self, text: str):
        self._messages.append({"role": "assistant", "content": text})
        self._persist("assistant", text)
        self._trim()

    def get_messages_for_api(self) -> list[dict]:
        return copy.deepcopy(self._messages)

    def clear(self):
        self._messages.clear()

    @property
    def messages(self) -> list[dict]:
        return self._messages
