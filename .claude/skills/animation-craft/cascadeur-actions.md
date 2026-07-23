# Cascadeur action IDs (call via cascadeur_action / call_action)

Extracted from the 2026.1.3 binaries. Any of these can be triggered headlessly
with `cascadeur_action(name)` (Python `ActionManager.call_action(name)`) — this
is the real "press the button without pressing it". Set the timeline
selection/current frame first (scene.set_frame, or the layers selector for an
interval).

## Interpolation (Timeline menu / interpolation selector)

Two variants each: `... on current frame` and `... on selected interval`.

- `Timeline.Bezier.Bezier on current frame` / `... on selected interval`
- `Timeline.Bezier clamped.Bezier clamped on current frame` / `... on selected interval`
- `Timeline.Bezier viscous.Bezier viscous on current frame` / `... on selected interval`
- `Timeline.Linear.Linear on current frame` / `... on selected interval`
- `Timeline.Step.Step on current frame` / `... on selected interval`
- `Timeline.Fixed.Fixed on current frame` / `... on selected interval`
- `Timeline.AI.AI on current frame` / `Timeline.AI.AI on selected interval`  ← ML inbetweening (see caveat)

Prefer the MCP `set_interval` op for Bezier/Linear/Step/Fixed — it sets the
section properties directly and reliably. The action IDs are a fallback and the
only way to reach modes without a section-property equivalent.

## Keys / timeline (Timeline menu)

- `Scene.Undo`, `Scene.Redo`
- `Timeline.Add`  (Add track)
- Menu labels that map to actions: "Add|Remove Key" (F), "Add|Remove Key On
  Interval" (Alt+F), "Change IK|FK Key" (Shift+F), "Change To Fulcrum Key"
  (Shift+R), "Set Timeline By Selected" (F6). Call by their action id if a
  direct op is missing.

## Tools (View.* — toggles/opens)

- `View.MocapTool`  (Video Mocap — UI/alpha only)
- `View.Inbetweening_RunRootMotion`  (generative Root Motion — **WORKS on free
  license!** wired as MCP tool `root_motion` / op `ai.root_motion`. Select an
  interval with >=2 keyframes across all tracks first, then call it; the log
  prints "Root motion: done". Extracts a world trajectory from in-place
  animation and drives the root by foot contacts. On error with no selection it
  prints "Root motion error: please select at least 2 key frames" — a FUNCTIONAL
  error, not a license dialog, which is how we confirmed it's not gated.)
- `View.AutoInterpolation_`, `View.AutoInterpolation_Keys`
- `View.Retargeting_`  (PAID — basic/indie blocked)
- `View.FixFoot`, `View.FixFoot_KeepKeyFrames`, `View.FixCollisions`
- `View.Animation unbaking`, `View.Composition`, `View.Silhouette mode`
- `View.AIstyle`, `View.AIdescription`  (inbetweening style/description inputs)

## AI Inbetweening caveat (verified 2026-07-23, build 2026.1.3, free license)

Setting `Timeline.AI` interpolation (via op, action id, OR a real mouse click on
the timeline AI button / "Inbetweening start" menu) makes the inbetween frames
**NaN and the character vanish** — confirmed in the LIVE foreground UI, not just
headless. There is no per-feature "Pro required" string for inbetweening in the
binary (unlike FBX export / AutoPhysics / Retargeting which DO have one), but the
app carries a general `isPaidFunctionalityAvailable` gate + `showPaidNotAvailable
Dialog`, and the feature silently produces no output here. Conclusion: AI
Inbetweening is not usable on this license/install — it is NOT a "button access"
problem, so no command or UI automation unlocks it. Use classic BEZIER splines +
breakdown keys (this skill's recipes) instead.

**Root Motion is NOT license-gated** (verified same day): `ai.root_motion` op /
`root_motion` MCP tool selects the interval and calls
`View.Inbetweening_RunRootMotion`; log confirms "Root motion: done", character
stays intact. So the two "Inbetweening_*" features behave oppositely here — AI
inbetween is gated/broken, Root Motion runs. Always distinguish a functional
error message (feature ran) from a "Feature not available / Upgrade" dialog
(license gate) — that's the reliable test for any tool.

**BUT Root Motion headless produces no forward travel on its own.** On a
walk-in-place with fulcrum-fixed stance feet, `root_motion` ran ("done") but the
character root (Hips joint AND the top Armature node) stayed at origin — no
locomotion generated. The feature needs a "root motion reference/style"
(the presets embedded in the tool: Walk / Ground / Jump / Fall / Acrobatic /
Combat, plus "please select root motion reference first") which is chosen in the
Inbetweening/Root-Motion UI panel, not reachable by the action id alone. So:
triggering the button headlessly is solved, but a USEFUL root-motion result
currently needs the UI panel to pick the reference. Practical stance: author
locomotion with explicit root translation via set_transforms (move Hips point in
world +Z per frame) rather than relying on generative Root Motion. Also: run it
ISOLATED (its own bridge session) + wait before the next call — hammering
python.exec right after "done" crashed the app.

## Bypassing UI-only features (general technique)

For genuinely UI-only tools with no working headless path, drive the real UI:
foreground the window (Alt-key trick + SetForegroundWindow), capture with
PrintWindow (PW_RENDERFULLCONTENT=2, works even when occluded), locate controls
visually, click with SetCursorPos+mouse_event. Reusable scripts:
scratchpad printwindow.ps1 (capture) and click_menu.ps1 (foreground+click).
This works for opening menus/dialogs; it does NOT make a license-gated compute
feature produce output.
