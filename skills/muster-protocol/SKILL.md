---
name: muster-protocol
description: Use when working against a Muster board (os_tasks in Directus) - the claim, work, verify, close protocol that keeps parallel agents off each other's toes and separates done from claimed-done.
---

# The Muster protocol

The task record, not this chat, is where work is represented. Chat is where you
think. The board is where the team agrees on what is done.

## The loop

1. **Claim before you work.** Read the row. Confirm it is unclaimed. Write your
   identity and an in-progress status. Then start.
2. **Work.** In your own worktree, off fresh trunk. Never edit a path another
   agent has claimed.
3. **Verify.** Prove the thing does what the row says. Run it, drive it, look at
   the output. "The tests pass" and "the system works" are different claims.
4. **Close with the receipt.** Record what you did, what you proved, and what is
   still open. A closing note with no evidence is not a close.

## The rules that make it hold

- **Check the board before you file.** A row you did not read is a row you will
  duplicate.
- **A blocked or pending note is a claim with an expiry.** Re-verify it live
  before you repeat it. Stale notes propagate into shipped artifacts.
- **Do not trust a green check.** A gate that skips reports success. Assert the
  artifact exists, not that the job exited 0.
- **Secrets are referenced, never printed.** If a value would render, route it
  somewhere else.
- **The row is not atomic.** Two agents can race it. Contention is controlled by
  disjoint dispatch and worktree isolation, not by the board existing.

## When this does not apply

Single-file fixes and anything that fits one window. The board is overhead you
should not pay for work that cannot outlive a session.
