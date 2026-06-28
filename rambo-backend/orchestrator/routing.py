"""Tier 1 — Smart routing (dispatch intelligence).

An LLM-backed router that reads an explicit routing policy plus the live
roster (core agents + skills + Factory-spawned manifests) and decides, on
purpose, either to:
  - ask ONE clarifying question (when genuinely ambiguous), or
  - dispatch an ORDERED list of steps (decomposing multi-step requests),

routing each step to a concrete target. Routing intelligence lives here in
the conductor; individual agents never see each other.

Falls back to the caller's keyword router when the LLM is unavailable or the
routing call fails — failure isolation (Tier 3) applies to the router too.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

import cache_config
import model_config

logger = logging.getLogger(__name__)


class RouteStep(BaseModel):
    target: str
    task: str


class RoutingDecision(BaseModel):
    mode: Literal["clarify", "dispatch"]
    question: str = ""
    steps: list[RouteStep] = Field(default_factory=list)


_EMIT_TOOL = {
    "name": "emit_routing_decision",
    "description": (
        "Emit the routing decision. Call this exactly once. Either ask one "
        "clarifying question (mode=clarify) or dispatch an ordered list of "
        "steps (mode=dispatch)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["clarify", "dispatch"]},
            "question": {
                "type": "string",
                "description": "The single clarifying question (mode=clarify only).",
            },
            "steps": {
                "type": "array",
                "description": "Ordered dispatch steps (mode=dispatch only).",
                "items": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "A target name from the roster."},
                        "task": {"type": "string", "description": "The task for that target, in natural language."},
                    },
                    "required": ["target", "task"],
                },
            },
        },
        "required": ["mode"],
    },
}

_POLICY = """\
You are the routing brain of R.A.M.B.O, a multi-agent operator. Your only \
job is to decide WHO handles a request and WHETHER to ask first. You do not \
do the work yourself.

Rules:
1. Pick targets ONLY from the roster below. Never invent a target name.
2. Ordering: a design/planning step must precede an implementation step. If a \
request needs planning then building, emit them as separate ordered steps \
(e.g. planner, then executor).
3. Decomposition: a multi-step request becomes MULTIPLE ordered steps, not \
one blurred step. A single focused request is one step.
4. Strongly prefer acting over asking. Default to dispatch: pick the \
best-fit target and act on your most reasonable reading of the request. \
Greetings, small talk, opinions, and any question you can simply answer in \
conversation go to the "converse" target — answer them, do NOT clarify them. \
Only set mode=clarify when the request is so ambiguous that you genuinely \
cannot choose a target AND acting on the wrong reading would waste real \
effort. When torn between two task targets, pick the more likely one and \
proceed. A vague-but-answerable request is never a reason to clarify — route \
it to "converse" and answer.
5. Clarify questions must sound HUMAN and natural — like a sharp assistant \
asking for a quick detail. NEVER expose internal mechanics: don't say "route", \
"agent", "dispatch", or "which agent". Bad: "Could you tell me what you'd like \
help with so I can route your request to the right agent?" Good: "Happy to \
help — what are you working on?" or "Sure — did you mean the weather, or \
something else?"
6. Prefer a specific skill or spawned agent when one squarely fits. Use \
"orchestrate" for open-ended, multi-agent build/research goals that need the \
full planning pipeline. Use a single mode (planner, executor, researcher) only \
for a focused task it owns.
7. Keep each step's task in natural language, phrased for that target.
8. MEMORY: any request to remember, save, store, note, memorize, recall, or \
look up something the operator told you ALWAYS routes to "keeper" — never to \
"converse" and never answered conversationally. "Remember X", "save this", \
"what did I tell you about X", "what's my X" → keeper.
9. MESSAGING: any request to email, notify, message, or text the operator \
("email me X", "send me a reminder", "notify me when...") ALWAYS routes to \
"notify" — never converse, never claim the backend is unavailable yourself \
(the skill reports its own status).
10. SELF-AWARENESS: any question about R.A.M.B.O's OWN code, source, repository, \
architecture, or recent changes ("what changed", "what did we just change", "your \
code", "how are you built", "what's in <file>") ALWAYS routes to the "codebase" \
skill — never "converse" and never answered from memory. R.A.M.B.O reads its own \
repo to answer these.
11. MUSIC: any request to play, pause, stop, skip, resume, or queue music or \
songs, play a playlist, control Spotify, or ask what's currently playing ALWAYS \
routes to "spotify". "play Daft Punk", "next song", "pause", "what's playing", \
"play my workout playlist" → spotify.
12. BUILD: any request to build, create, make, write, or generate a NEW \
standalone app, tool, script, game, website, or program ALWAYS routes to \
"build" — never "orchestrate" and never "converse". "build me a typing speed \
app", "create a calculator", "make a tool that…", "write me a script that…" → \
build. The "build" target actually writes the files; "orchestrate" only plans \
and must NOT be used to fulfill a concrete build request. Use "orchestrate" \
ONLY for open-ended research/strategy goals that are not a single buildable \
artifact.
13. DOMAINS: route by subject — news/headlines/current events → "news"; stock, \
market, ticker, or crypto prices → "finance"; reading/checking email or the \
inbox → "gmail"; controlling lights/switches/thermostat/locks or any smart-home \
device ("turn off the lights") → "smart-home". These are concrete actions, not \
"converse".
14. WATCHLIST: managing what RAMBO keeps an eye on → "watchlist". "keep an eye \
on X", "watch/track/monitor X", "stop watching X", "what am I watching" (watch \
topics); and "remind me X is due <date>", "add a deadline …", "what are my \
deadlines" (deadlines). These ADD/manage watch items — route to "watchlist", NOT \
"keeper" (keeper is for general remember/recall), and NOT "calendar".
15. FOLLOW-UPS & AFFIRMATIONS: the messages above are the recent conversation. If \
the latest message is a short confirmation or continuation ("yes", "yeah", \
"sure", "ok", "go ahead", "do it", "please", "that one", "the first one") or only \
makes sense as a reply to the previous turn, USE the conversation to recover the \
ACTUAL intent and route THAT (e.g. you offered a web search for today's games and \
they said "yes" → route web_search for today's games). Never route the literal \
"yes", and NEVER attach a follow-up to an unrelated finished task from earlier.
16. FACTUAL LOOKUPS: questions seeking current facts you can't answer from memory \
— sports schedules/scores, "what teams are playing", "who's playing", standings, \
general knowledge, "look up X" — route to "web_search" (or "news"/"finance" when \
the subject squarely fits). A plain question is NEVER "build" and NEVER \
"orchestrate".
17. STATUS / UPDATE: a general request to be brought up to speed — "give me an \
update", "catch me up", "system status", "status report", "sitrep", "where are \
we", "what have we been working on", "bring me up to speed" — ALWAYS routes to \
the "system_update" skill (it reports recent changes + suggested next targets + \
what's pending). Dispatch it directly, do NOT clarify. This is distinct from \
file-specific code questions ("what's in <file>", "what changed in X") which go \
to "codebase".

18b. GIT (RAMBO's OWN repo), all operator-confirmed:
  - "push to github", "commit and push", "push my changes", "save to github" → \
"git_push" (STAGES a push for approval — never auto-pushes).
  - "merge feature-x into main", "merge the dev branch" → "git_merge" (STAGES a \
local branch merge).
  - "merge PR #12", "merge pull request 7" → "pr_merge" (STAGES a GitHub PR merge).
  - approving/denying ANY of the above — "approve the push", "approve the merge", \
"deny the merge", "cancel it" — → "resolve_git".
18c. STRIKEOUT WATCH: "strikeout watch", "strikeout board", "who's striking out", \
"best strikeouts", "strikeout parlay" → the "strikeout_watch" skill (ranks the \
day's probable starters by P(8+/9+/10+ Ks) for alt-strikeout parlays). This is the \
pitcher-K board, distinct from the betting "daily-edge" Pick6 markets.
18d. HITS & TOTAL BASES: "hits watch", "total bases board", "hits and total bases", \
"hits parlay" → the "hits_tb_watch" skill (ranks hitters by P(1+ hit) and P(2+ \
total bases) for hits/total-base parlays).
18. DELETE A BUILD: removing/deleting an EXISTING build the operator already made \
("delete the calculator build", "remove my snake game build", "get rid of that \
build", "trash that build") → the "delete_build" skill. This is the opposite of \
"build" (which CREATES a new project) — never route a deletion to "build".

ROSTER:
{roster}

Respond by calling emit_routing_decision exactly once."""


def build_policy(roster_lines: list[str]) -> str:
    return _POLICY.format(roster="\n".join(roster_lines))


class SmartRouter:
    def __init__(self, llm_client, model: str | None = None):
        self._llm = llm_client
        self._model = model or model_config.default_model()

    async def route(
        self,
        goal: str,
        roster_lines: list[str],
        valid_targets: set[str],
        history: list[dict] | None = None,
    ) -> RoutingDecision | None:
        """Return a validated RoutingDecision, or None to signal fallback.

        `history` is the recent conversation (clean {role, content} turns) so the
        router can interpret follow-ups and affirmations ("yes", "do it") against
        what was just discussed instead of routing them in isolation."""
        if not self._llm:
            return None
        messages = [*(history or []),
                    {"role": "user", "content": f"Route this request: {goal}"}]
        try:
            response = await self._llm.messages.create(
                model=self._model,
                max_tokens=1024,
                system=[{
                    "type": "text",
                    "text": build_policy(roster_lines),
                    "cache_control": cache_config.cache_control(),
                }],
                messages=messages,
                tools=[_EMIT_TOOL],
                tool_choice={"type": "tool", "name": "emit_routing_decision"},
            )
        except Exception:
            logger.exception("Smart router LLM call failed — falling back")
            return None

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "emit_routing_decision":
                try:
                    decision = RoutingDecision(**block.input)
                except Exception:
                    logger.exception("Router emitted invalid decision — falling back")
                    return None
                return self._sanitize(decision, valid_targets)

        logger.warning("Router did not emit a decision — falling back")
        return None

    @staticmethod
    def _sanitize(decision: RoutingDecision, valid_targets: set[str]) -> RoutingDecision | None:
        if decision.mode == "clarify":
            if not decision.question.strip():
                return None
            return decision
        # dispatch: keep only steps with known targets. Unknown → "converse"
        # (just answer) rather than "orchestrate", whose simulated build pipeline
        # turns stray routes into a misleading fake-build.
        cleaned: list[RouteStep] = []
        for step in decision.steps:
            target = step.target if step.target in valid_targets else "converse"
            cleaned.append(RouteStep(target=target, task=step.task or ""))
        if not cleaned:
            return None
        decision.steps = cleaned
        return decision
