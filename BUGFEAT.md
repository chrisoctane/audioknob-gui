# Next Features (Backlog)

This file collects future ideas only. Nothing here is committed work until it is moved into `PLAN.md` and implemented.

## Ideas

- UI refresh pass for layout/spacing polish (after stability)
- Continuous jitter monitor dialog
  - Add a "Monitor" action on the jitter test row that opens a popup.
  - Runs cyclictest continuously (or long duration) and parses output periodically.
  - Live per-thread table: thread id, current max/avg, running best/worst.
  - Stop button writes a final summary into the jitter knob info pane and logs the raw output.
  - Goal: help users identify lowest-jitter cores for JACK pinning.

## Bugfix Backlog (Next Release)

- ~~Test bug: "this is a test, bug. fix me."~~ (fixed)
- Kernel cmdline knobs should allow restoring to Tumbleweed defaults even if they were set before audioknob:
  - threadirqs
  - kernel audit
  - cpu mitigations
- RT limits still not surfacing a reboot/log-out requirement; investigate why banner/prompt can be missed.
- QjackCtl cores popup should read the actual config and pre-select cores (default 0,1 after apply).
- Status check UI should not reserve space before use; consider popup or moving controls into main table.
