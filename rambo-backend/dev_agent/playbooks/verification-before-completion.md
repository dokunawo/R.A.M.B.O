# Verification Before Completion

Evidence before claims. Never describe work as done, fixed, or passing without
something concrete to point to.

**When you finish:**
- State exactly what you changed, file by file, in plain language.
- Point to the evidence a reviewer can check: the test you added and its
  `run_tests` result, the specific lines you edited, the behavior that now differs.
- If your change is testable, you MUST have run `run_tests` and seen it pass
  before claiming it works — cite that result. Only claim "tests pass" when
  `run_tests` actually returned passed in this session.
- Don't claim a build runs or the app works — you can't run those here; say what
  you changed and what you verified (the tests).
- If you were unable to fully do the task, say so and explain what's missing.
  An honest partial result is worth more than a false "done."

**Scope check before finishing:**
- Did you touch only the files the task needed? If you changed something extra,
  either justify it or revert it.
- Re-read your own diff in your head. Would the operator be surprised by anything
  in it? If yes, call it out explicitly.
