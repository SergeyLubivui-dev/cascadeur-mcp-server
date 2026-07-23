---
name: animation-craft
description: Rules for posing and animating humanoid characters in Cascadeur via the cascadeur MCP tools. Load BEFORE creating or editing any pose, keyframe, or animation - covers the 12 animation principles mapped to concrete MCP operations, humanoid balance/IK rules, timing tables, and pose recipes (sit, stand, walk, jump).
---

# Animation craft for Cascadeur MCP

Apply these rules whenever building poses or animations with the `cascadeur` MCP
tools. Goal: poses that are physically plausible and animation that reads well.
Details and recipes: [humanoid-rules.md](humanoid-rules.md).

## The official Cascadeur pipeline (blocking → spline → physics)

Cascadeur is designed around AI-assisted posing, NOT hand-placing every point.
The intended order (per cascadeur.com/help): **1) Blocking** key poses with
AutoPosing → **2) Spline** (interpolation + IK/FK) → **3) Inbetweening** (AI
fill, optional) → **4) Physics** (AutoPhysics: balance, ballistics, secondary
motion). Match this. What's usable headless on the free license: AutoPosing
(yes), interpolation (yes), FBX via our baker (yes). Gated/UI-only: AI
Inbetweening (NaN), full AutoPhysics (Pro + no script API — turn_off only),
video mocap (UI). So we do blocking+spline cleanly; physics refinement needs the
Pro UI.

## AutoPosing is the posing method — set FEW controllers, not all

The rig has AutoPosingLink behaviours (~one per point). When you move a few
controllers, the neural net completes a natural full-body pose automatically —
you do NOT hand-place all ~20 points. VERIFIED: setting only hips + both feet to
a crouch produced a correct pose (arms hang, knees bend, torso upright) with no
other input. So BLOCK POSES WITH 3-6 DEFINING CONTROLLERS:
- Always: both feet (contacts — ankles are always active) + hips (the intent).
- Add only what the pose needs: a hand for a reach, head for a look.
- Then optionally `auto_pose_update()` to let the ML refine.
- Let AutoPosing fill knees, spine, shoulders, unmoved arm, etc.
This is faster and more natural than specifying every point. Over-specifying
(the old way) fights the AI and looks stiffer.

## Workflow (pose-to-pose, always in this order)

1. **Prepare**: `import_fbx(mode="model", new_scene=True)` → `auto_rig(template)`.
   Then ALWAYS call `bone_map()` — it classifies joints of ANY naming convention
   (Mixamo/UE/CC/Daz/custom) into canonical roles and links each to its
   controller points. Address bones by ROLE, never hardcoded names. Note limb
   lengths; never place an IK target past ~95% of the chain length.
2. **Block key poses with AutoPosing**: set the FEW defining controllers
   (feet + hips + intent), one `set_transforms` per pose frame; let autoposing
   complete the body. Contacts first. Optionally `auto_pose_update()`.
3. **Check every pose visually**: `viewport_screenshot()` after each key pose.
   A good pose reads as a silhouette. Fix before moving on.
4. **Timing**: shift keys with `keyframes` until the beat feels right.
5. **Spline**: `set_interval(interpolation="BEZIER")` per interval.
6. **Polish**: breakdowns for arcs, 2-4 frame offsets for follow-through,
   settle keys after stops.
7. **Verify in motion**: render frame sequence, inspect arcs and foot sliding.
8. **(Physics — Pro/UI only)**: if available, apply AutoPhysics for balance +
   ballistic trajectories + secondary motion. Headless/free: skip, keep contacts
   fulcrum-fixed and trajectories hand-arced.
9. **Deliver**: `export_animation(format="fbx")` + `scene_manage(action="save")`.
   For existing mocap onto a matching skeleton, prefer `retarget_animation`.

## The 12 principles → concrete MCP actions

1. **Squash & stretch** — for realistic humanoids: spine compression. On impact
   frames bring Spine/Spine1 points closer to Hips (2-4% height); stretch on
   airborne extremes.
2. **Anticipation** — before any main action insert an opposite move 4-8 frames
   earlier: crouch before jump, lean back before running forward, hips
   up/forward before sitting.
3. **Staging** — before rendering, pick a camera angle where the action reads
   (¾ view usually). One action at a time; don't move everything at once.
4. **Straight-ahead vs pose-to-pose** — always pose-to-pose (workflow above):
   key poses → breakdowns → spline.
5. **Follow-through & overlapping action** — children lag parents: when the
   torso stops, offset head/arm keys +2..4 frames; add a small overshoot key
   then settle back over 4-8 frames.
6. **Slow in / slow out** — BEZIER intervals give this; strengthen by adding a
   breakdown key at ~70-80% of the travel 2-3 frames before the pose lands.
7. **Arcs** — hands/head travel in arcs. After splining, sample mid-frames
   (`get_transforms` at N/2): if the midpoint lies on the straight line between
   poses, add a breakdown offset perpendicular to travel (usually up/outward).
8. **Secondary action** — after the body works: head gaze shifts, finger
   curl/spread, weight shifts. Small offsets on Neck/Head and hand points.
9. **Timing** — at 30 fps: snappy action 4-8 frames, normal gesture 12-20,
   full-body transition (sit/stand) 24-40, hold poses 8-16 frames before the
   next action. Never even spacing everywhere — vary.
10. **Exaggeration** — push blocked poses ~10-15% past realistic (deeper crouch,
    bigger lean); physics-plausible but expressive.
11. **Solid posing** — no perfectly straight limbs, no exactly mirrored
    left/right, weight visibly on one leg or both. Check silhouette per pose.
12. **Appeal** — asymmetry everywhere: pelvis tilted a few degrees, one hand
    higher, head slightly rotated. Symmetric poses read robotic.

## Non-negotiable humanoid constraints (full list in humanoid-rules.md)

- **Balance**: center of mass (≈ Hips point, plus lean of torso) stays over the
  support polygon (area between planted feet). Deep sit/crouch → torso leans
  forward to compensate hips going back.
- **Feet plant**: identical foot XZ across keys while grounded (or
  `set_interval(fixation="fulcrum")` on the interval). Any foot slide is a bug —
  verify with `get_transforms` on foot points across frames.
- **Knees track toes**: knees bend forward/slightly outward, never inward
  (valgus) or backward.
- **Chain limits**: distance(shoulder→hand target) < 0.95 × arm length;
  distance(hip→foot) < 0.98 × leg length when standing.
- **Head stabilizes**: gaze direction changes less and later than the torso.

## Rig integrity (never break the rig)

- Write ONLY to controller point inputs (set_transforms handles this) — never
  delete behaviours, points, or rig objects; never write to computed outputs.
- Fingers/joints WITHOUT controller points cannot be animated (they follow the
  hand rigidly); direct joint-data writes are ignored by the update graph. If
  finger animation is needed, the character must be rigged with a full-finger
  template (all 5 fingers present in the skeleton), or finger rig elements
  added in rig mode.
- `Interpolation.AI` (ML inbetweening) is UNUSABLE on this license/build
  (2026.1.3, free): setting it — by op, by action id
  `Timeline.AI.AI on selected interval`, OR by a real mouse click in the live
  UI — makes the interval NaN and the character vanish. Verified in the
  foreground UI, so it is NOT a "button access" problem; no command or UI
  automation unlocks it (details + action-id list: cascadeur-actions.md). Do
  NOT use AI interpolation; use BEZIER + breakdown keys. If a scene ever goes
  NaN, restore from `%LOCALAPPDATA%/Nekki Limited/Cascadeur/autosave/`. Save a
  .casc before any AI experiment.

## Cascadeur AI features — use them, in this order

- `auto_pose_update()` after moving a few main points — Cascadeur's ML
  autoposing adjusts secondary points to a natural pose (the rig is created
  with autoposing on).
- `mirror(what="frame")` for symmetric pose halves.
- AutoPhysics / fulcrum fixation for physically-correct contact (interval
  `fixation="fulcrum"` on planted feet).
- Do NOT call video render (`play_to_video_file` quits the app on this
  license); render PNG sequences via `viewport_screenshot` per frame.
