# Systematic Debugging

Find the root cause before changing anything. A fix that targets a symptom
without understanding the cause usually creates a new bug.

**For any bug fix, before you edit:**
1. **Read the error precisely.** Stack traces, line numbers, and messages often
   name the exact problem. Don't skim them.
2. **Reproduce it in your head from the code.** Read the failing path end to end
   (use read_file / grep across the involved files) until you can explain *why*
   it fails, not just *where*.
3. **Check what changed.** Look at the code around recent edits; bugs usually
   live near the last change to that area.
4. **State the root cause** in one sentence before writing the fix. If you can't,
   you don't understand it yet — keep reading.

**Then fix the cause, not the symptom:**
- Change the smallest thing that addresses the actual cause.
- Don't add broad try/except, defensive guards, or retries to paper over a
  failure you haven't explained.
- If the real fix is out of scope for the task, say so rather than hacking around
  it.
