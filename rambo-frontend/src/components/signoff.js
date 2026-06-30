// Tier 5 — "know when to stop." A small, deterministic check that decides whether
// an utterance is a pure sign-off ("okay thanks", "sounds good", "got it") so the
// assistant can let the conversation END instead of manufacturing one more reply.
//
// Design rule: bias HARD toward replying. Staying silent when the operator wanted a
// reply reads as broken; replying to a borderline goodbye is just the mild old
// behavior. So this only fires on a SHORT utterance that clearly signs off and has
// no question / command / "leading into new info" signal. Tune the lists below — a
// miss is a one-line change. Pure function (no React) so it's unit-testable.

// Clear farewell / gratitude / acknowledgement tokens.
const SIGNOFF_TOKENS =
  /\b(thanks|thank you|thank u|thx|got it|sounds good|will do|appreciate it|much appreciated|right on|bye|goodbye|see ya|see you|catch you later|talk later|i'?m good|we'?re good|all good|i'?m done|that'?s all|that'?s it|nothing else|that'?ll be all)\b/;

// Bare positives that ONLY count as an ending in a very short utterance — in a
// longer sentence they're almost always leading into something ("great, so …").
const BARE_POSITIVE = /^(ok|okay|cool|great|nice|awesome|sweet|alright|word|bet|gotcha|roger|copy|perfect|excellent)$/;
const FILLER = /^(thanks?|thank|you|rambo|operator|man|dude|bro|sir|now|then|much|appreciated|it)$/;

// A question — wants something back.
const QUESTION = /[?]|\b(can you|could you|would you|will you|how about|what about|one more thing|what'?s|whats|how'?s|hows|how do|how can|when|where|why|who|which|do you|are you|is there|tell me|give me)\b/;

// An imperative command — an instruction, not a farewell ...
const COMMAND = /\b(send|open|play|pause|resume|set|turn|show|pull|find|search|look up|remind|add|start|call|text|email|schedule|create|make|build|run|check|read|write|cancel|delete|remove|stop|mute|unmute|volume|navigate|go to)\b/;
// ... UNLESS the operator is committing to do it themselves ("great, I'll send that").
const SELF_COMMIT = /\b(i'?ll|i will|i'?m gonna|i am gonna|i'?m going to|i am going to|let me|on it)\b/;

/**
 * True only when `text` is a pure sign-off. Conservative by design.
 * @param {string} text
 * @returns {boolean}
 */
export function isSignoff(text) {
  const raw = (text || "").toLowerCase().trim();
  if (!raw) return false;
  const t = raw.replace(/[.,!?]+$/g, "").trim();          // strip trailing punctuation
  if (!t) return false;
  const words = t.split(/\s+/).filter(Boolean);

  // Real goodbyes are brief. A long sentence is almost never a pure sign-off.
  if (words.length > 6) return false;

  // Vetoes — anything that wants a response replies normally.
  if (QUESTION.test(raw)) return false;
  if (COMMAND.test(t) && !SELF_COMMIT.test(t)) return false;

  const hasToken = SIGNOFF_TOKENS.test(t);
  if (hasToken) return true;

  // No explicit token: allow ONLY a bare positive (optionally with filler like
  // "thanks"/a name), and only when very short — otherwise it's leading into new
  // info ("okay so the revenue is up") and should get a reply.
  if (words.length > 2) return false;
  return words.every((w) => BARE_POSITIVE.test(w) || FILLER.test(w))
    && words.some((w) => BARE_POSITIVE.test(w));
}
