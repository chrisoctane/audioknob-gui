# Next Features (Backlog)

This file collects future ideas only. Nothing here is committed work until it is moved into `PLAN.md` and implemented.

## Ideas

- Continuous jitter monitor dialog
  - Add a "Monitor" action on the jitter test row that opens a popup.
  - Runs cyclictest continuously (or long duration) and parses output periodically.
  - Live per-thread table: thread id, current max/avg, running best/worst.
  - Stop button writes a final summary into the jitter knob info pane and logs the raw output.
  - Goal: help users identify lowest-jitter cores for JACK pinning.
