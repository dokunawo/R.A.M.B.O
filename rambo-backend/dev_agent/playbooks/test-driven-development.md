# Test-Driven Development

Write the test first, then the implementation. If a behavior isn't covered by a
test, you don't know it works.

**For any feature or bug fix — the full red-green loop:**
1. Find or create the test file next to the code (mirror the project's existing
   test layout and framework — read a sibling test first).
2. Write a minimal test that captures the desired behavior. For a bug fix, write
   a test that reproduces the bug.
3. **Run it with `run_tests` and watch it FAIL** — this proves the test actually
   tests the right thing. If it passes before you've written any code, the test
   is wrong; fix it.
4. Write the smallest implementation that makes the test pass.
5. **Run `run_tests` again and watch it PASS.** If it still fails, read the
   output and fix the implementation (not the test) — repeat until green.
6. Leave both the test and the implementation in the change.

**Rules:**
- Don't write production code for a behavior with no test.
- Don't delete or weaken an existing test to make your change "pass."
- Match the project's assertion style and naming — don't introduce a new test
  framework.
- Keep `run_tests` narrow (the specific test you wrote) so it's fast.
