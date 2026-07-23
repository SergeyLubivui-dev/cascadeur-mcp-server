# Humanoid posing rules & recipes (Cascadeur MCP)

Units: centimeters, Y up, character faces +Z. Frame rate 30 fps.
Controller naming (auto_rig output): `<namespace>:<Joint>_MainPoint`,
`_AdditionalPoint` (orientation helper — move together with MainPoint to
preserve segment orientation, offset it to twist), `_DirectionPoint` (aim),
foot `_Self0Point` (heel). Write positions via `set_transforms`
(`global_position`); the op routes to the point's `Position` input and keys the
track.

## Measure the rig first

`rig_joints()` → record: hips height H (≈97 for MtbBiker2), thigh T (≈40.6),
shin S (≈37.9), arm: upperarm ≈23.6 + forearm ≈23.2, shoulder width ≈2×6.5.
All pose numbers below scale by H/97.

## Balance / weight

- Standing: COM (a point ~2cm in front of Hips joint) projects between the
  feet. Single-leg: COM over the planted foot; free leg + arms counterbalance.
- Hip hinge rule: hips move back by ΔZ → torso (Spine1/Spine2 points) leans
  forward so the head stays roughly over the feet; head Z ≈ midfoot Z ± 10.
- Sitting: weight transfers to the seat — torso can be upright; before contact
  (descent) the hip-hinge rule applies fully.
- Carrying/reaching with one arm: pelvis shifts a few cm to the opposite side.

## Legs

- Planted foot: identical world XZ on every key while grounded; heel drops to
  ankle-height (≈12.7), toes stay near ground contact. Use interval
  `fixation="fulcrum"` for hard plants.
- Knee (Leg_MainPoint) always in front of the hip-ankle line, tracking over the
  toes; sideways deviation < half foot width.
- Max comfortable squat: hips ≈ knee height (≈45-50); deeper needs heels up.
- Step length walk ≈ 0.4×H, run ≈ 0.65×H.

## Arms & hands

- Relaxed stand: hands hang at ~55-60% of H, slightly in front of thighs,
  elbows a few cm out from the ribs, bent 5-15°.
- Elbow (ForeArm point) points back/down-out; never inward past the ribcage.
- Reaching: shoulder (Shoulder_MainPoint) extends 3-6cm toward the target
  before the elbow straightens past 80%.
- Hands on knees (sitting): palm points ≈ knee point ± 5cm, elbows out.

## Spine & head

- Neutral spine is a shallow S; when bending, distribute rotation: pelvis 40%,
  Spine 30%, Spine1 20%, Neck/Head 10%.
- Head counter-rotation: keep gaze target stable until the torso finishes ~70%
  of its turn, then the head leads the next action.

## Timing tables (30 fps)

| Action | Total frames | Key layout |
|---|---|---|
| Sit down | 28-40 | stand 0 → anticipation (hips +2..3 up, lean fwd) @4-6 → descent mid @40-50% → contact @75% → settle overshoot ~3% @+3 → rest |
| Stand up | 24-36 | lean fwd + feet pull back @0-20% → weight over feet @40% → rise → settle |
| Walk cycle | 32 (loop) | contact 0/16, down 4/20, passing 8/24, up 12/28 |
| Jump | prep 8-12, air by physics, land 6-10 | crouch → launch (full extension) → air arcs → land crouch → settle |
| Head turn | 8-14 | anticipation 2fr opposite → turn → 2fr overshoot → settle |

## Sit-down recipe (refined, on top of what worked)

Offsets from the standing pose, scaled by H/97 (ΔX, ΔY, ΔZ):

| Points | Anticipation @f5 | Mid @f14 | Contact @f26 | Settle @f30 |
|---|---|---|---|---|
| Hips_Main/Additional | 0,+1,+2 | 0,-20,-8 | 0,-45,-18 | 0,-43,-18 |
| Spine_* | 0,+1,+3 | 0,-18,-2 | 0,-44,-14 | 0,-42,-14 |
| Spine1_* | 0,0,+4 | 0,-15,+3 | 0,-42,-9 | 0,-40,-10 |
| Neck/Head_Main | 0,0,+4 | 0,-12,+6 | 0,-40,-4 | 0,-39,-6 |
| Shoulder_* | 0,0,+3 | 0,-13,+5 | 0,-41,-5 | 0,-40,-6 |
| Arm_Main | 0,0,+2 | 0,-13,+5 | 0,-40,+2 | 0,-39,+1 |
| ForeArm_* | 0,0,+2 | 0,-10,+9 | 0,-32,+8 | 0,-31,+7 |
| Hand_* | 0,0,+2 | 0,-7,+13 | 0,-27,+15 | 0,-26,+14 |
| UpLeg_* | 0,0,0 | 0,-20,-7 | 0,-45,-16 | 0,-43,-16 |
| Leg_* (knees) | 0,0,0 | 0,-2,+11 | 0,-4,+18 | 0,-4,+18 |
| Foot/Toe points | 0,0,0 | 0,0,+4 | 0,0,+7 | 0,0,+7 |

Then: BEZIER on every interval EXCEPT after the last key (STEP holds); check
arcs of Head and Hand at f10/f20 — offset up/forward if the path is straight.
Asymmetry pass: right hand -2cm Y vs left, head yaw 3-5°, pelvis roll 2°.

## Walk cycle recipe (32 frames, loops; step ≈ 0.4×H ≈ 39)

Poses at right-foot timing; left is the same +16 frames. All keys per pose on
STEP first, BEZIER after. Root (hips) stays at X=0; feet alternate.

| Frame | Pose | Hips (ΔY, ΔZ from stand) | Feet | Arms (opposite to legs) |
|---|---|---|---|---|
| 0 | Contact R | -3, 0 | R heel at +19.5 fwd, L toe at -19.5 | L arm fwd +12, R arm back -12 (Δ hand Z), swing from shoulder |
| 4 | Down R | -5 (lowest) | R flat planted, L lifting | passing |
| 8 | Passing R | -2 | R planted mid, L knee fwd, L foot at ankle height +8 up | arms passing thighs |
| 12 | Up R | -1 (highest) | R heel rising, L reaching fwd | R arm fwd starts |
| 16 | Contact L | -3, 0 | mirror of frame 0 | mirror |
| 32 | = frame 0 | loop | loop | loop |

Details: pelvis yaws ±4° toward the reaching leg, tilts ±3° down on the free
side; torso counter-rotates ~60% of pelvis yaw; head steady. Feet: fulcrum
fixation while planted; toe-off peels heel first, landing is heel-first then
`toe` down over 2-3 frames. Hands trace an arc, not a line.

## Transferring reference motion onto a character (two paths)

- **Same skeleton naming (both Mixamo/UE/CC etc.) → native import.**
  `retarget_animation(fbx_path)` (Cascadeur's `import_animation`) maps FULL joint
  transforms — position AND rotation — by joint name onto the current rigged
  character. Orientation is preserved, poses look clean. VERIFIED: importing
  "Strut Walking" onto the biker gave a correct, untwisted walk. This is the
  default for whole-clip motion transfer.
- **Different skeleton / single pose / partial limb → dataset (pose_apply).**
  The dataset stores reference joint WORLD positions per frame; pose_apply drives
  the target rig points to them (scaled by hip height). Good for borrowing a pose
  or one limb, and for skeletons whose names don't match. LIMITATION: position
  only — it does NOT carry segment orientation/twist, so a full body applied this
  way can look "crooked" (spine/limbs may twist). Use it for reference/analysis
  and partial poses; use native import for clean full motion.
- **In-place → travel**: reference walks are in-place (hips don't advance). After
  retargeting, add forward motion with the root-translation recipe below, or run
  root_motion.

## Reading a real walk cycle (measured from Mixamo "Strut Walking", 44f @30fps)

Ground truth extracted by importing the FBX and reading joint world positions.
Use these ratios (scale by your character's hip height H; this rig H≈100).

- **It is IN-PLACE**: hips net forward travel ≈ 0 over the whole clip. All the
  locomotion lives in the FEET sliding backward during stance. Mixamo/mocap
  walks are authored this way — to make the character travel you either add root
  translation (see next section) or run Root Motion. Two valid reference frames
  for the SAME motion: feet-slide+hips-static (in-place) vs feet-fixed+hips-move
  (world-locked). Pick one and be consistent.
- **Cadence**: full cycle = 44 frames = 2 steps → ~22 frames/step (a slow
  strut). A brisk walk is ~16f/step, jog ~11f/step.
- **Stride (foot Z)**: each foot slides from front +36 to back −34 ≈ **70cm
  peak-to-peak**, and the slide during stance is nearly LINEAR (constant ground
  speed) — that linearity is the signature of a planted foot. Swing returns it
  to front along an arc.
- **Foot contact (foot Y)**: flat on the ground (Y≈10, its minimum) for ~12–16
  frames (~35–40% of the cycle) = the stance/plant. Then lifts to ~25 (**≈15cm
  clearance**) at swing peak, back down to a heel-strike. Heel-strike → flat →
  toe-off are the three foot events to key.
- **Hip vertical bob (Y)**: ~**5cm**, TWO bobs per cycle (one per step).
- **Hip lateral sway (X)**: this strut sways ~**11cm** toward the stance leg
  (big, stylised). A natural walk uses ~2–4cm; never zero — flat X reads robotic.
- **Arms**: large smooth counter-swing (~40cm range here), each arm opposite its
  same-side leg, roughly sinusoidal.
- **Feet cross toward the centerline** (strut trait): plant near X≈0 instead of
  hip-width. A normal walk keeps feet ~hip-width; narrow it for a strut/catwalk.

Keyframe-building order this implies: (1) key the two CONTACTS per foot first
(heel front + toe-off back = the stride extremes), (2) key the PASSING pose
(swing foot beside stance foot, hip at its bob extreme, body balanced over the
stance foot), (3) add hip bob + lateral sway, (4) arm swing opposite legs,
(5) spline, (6) check the planted foot doesn't slide off its line.

## Forward walk with real root travel (VERIFIED WORKING, headless)

Generative Root Motion needs a UI reference and yields no travel headlessly, so
author locomotion DIRECTLY with explicit root translation. This is the reliable
method (proven: hips advanced -1.5→73cm, feet planted without sliding, baked to
FBX with exact round-trip). Model = body moves forward continuously; each foot
is FIXED in world during stance, swings ahead to the next plant.

Cycle 32 frames, forward speed V cm/frame (V≈2.5 → 80cm/cycle, step≈40cm). Keys
at 0/8/16/24/32. `adv(f) = V*f`.

- **Hips_MainPoint**: X=0, Z = restZ + adv(f), Y bob (contact 87 / passing 91).
- **Right foot**: plant world Z = P_r during stance (SAME value on f0,f8,f16 —
  fixed, no slide), Y=12.7; swing f16→32 lifts (Y=24 at f24) to next plant
  P_r + 2·step at f32.
- **Left foot**: opposite phase — swing f0→16 (lift Y=24 at f8) landing at plant
  P_l = P_r + step (f16), then FIXED at P_l on f16,f24,f32.
- **ToeBase point**: follow its foot: Z = footZ + 14, Y = 3.4 planted / 15 lifted.
- **Hands**: Z = restZ + adv(f) + swing, swing opposite the same-side leg
  (±10, 0 at passing). X,Y at rest.
- **Fulcrum** (critical, no foot slide): set fixation="fulcrum" (interval AND
  on_key) on each foot's STANCE keys — right f0/f8/f16, left f16/f24/f32 (+f0).
- BEZIER on every interval; leave STEP only after the last key.

Loop consistency: over one cycle every controller advances by exactly V·32, so
frame 32 == frame 0 shifted forward — the clip tiles seamlessly. For continuous
walking, repeat the pattern adding adv() cumulatively, or loop the 32f clip and
let the importer accumulate root motion.

Build it in FEW batched bridge sessions (one batch for all pose frames, one for
all fulcrum+BEZIER+save) — many tiny sessions stall. Verify by reading the Hips
JOINT global_matrix Z across frames (should rise steadily) and each stance
foot's world Z (should stay flat while planted).

## Run cycle (20-24 frames/loop)

Same structure, plus: both feet airborne 2-3 frames after each push-off; hips
ΔY amplitude ±8; torso leans fwd 12-18°; arms bent ~90° pumping shoulder-high;
step ≈ 0.65×H. Contact under the hips, not ahead (avoid overstride).

## Jump in place (prep 10 + air + land 10)

| Frame | Pose |
|---|---|
| 0 | stand |
| 4-8 | anticipation crouch: hips -25..-30, arms swing BACK -20, torso fwd 15° |
| 10 | launch: full extension, hips +5 above stand, arms thrown up/fwd, toes last contact |
| air (physics) | body arcs; knees tuck +15 fwd on ascent; prepare legs fwd for landing |
| touch | contact toes→heel, knees bend immediately |
| +3 | deepest absorb: hips -30, arms fwd for balance |
| +8-10 | settle to stand (slight overshoot up +2 then rest) |

Use ballistic timing: total air frames ≈ 2×sqrt(2×jump_height/980)×30.
Jump 30cm ≈ 15 frames air; 50cm ≈ 19 frames.

## Grab / reach (14-20 frames)

1. f0: idle. 2. f2-3: EYES/head turn to target first. 3. f4-6: torso+shoulder
lean toward target (anticipation, hand still). 4. f6-12: hand travels in an
ARC to the target (add breakdown above the straight line); elbow leads first
half, hand leads second half; hand overshoots +2cm at f12. 5. f13-15: settle
onto object; wrist aligns (use hand AdditionalPoint/DirectionPoint for
orientation). 6. Retract: reverse but slower (+30% frames), torso straightens
first, arm follows.
Fingers: only if the rig has finger points (bone_map → fingers.controllers).

## Swing / wind-up (punch, chop, throw: 16-24 frames)

| Phase | Frames | Rules |
|---|---|---|
| Wind-up | 6-10 | everything moves OPPOSITE to strike: arm back, pelvis+torso rotate away 20-40°, weight to back foot (hips shift -6 X toward it) |
| Strike | 3-5 | FAST. Order: pelvis rotates first, torso +1fr, shoulder +1fr, hand last (whip); weight transfers to front foot; hips drop -4 |
| Contact/extreme | 1-2 | fully extended pose held 1-2 frames, exaggerate line of action |
| Follow-through | 4-6 | arm continues past target and decelerates; torso over-rotates slightly |
| Recovery | 6-10 | slow return to guard/idle |

## Turn while moving / turn in place

- In place 90°: 12-16 frames. Order: eyes/head lead (f0-3), then shoulders
  (f2-6), pelvis (f4-10), feet STEP-pivot: outside foot steps first, inside
  pivots; never rotate planted feet in place (foot slide bug).
- Turning while walking: bank the whole body 3-8° INTO the turn; inner step
  shortens, outer lengthens; pelvis yaw leads the path tangent by ~10°; head
  looks into the turn 4+ frames before the body.
- 180° turn: 18-24 frames, 2 steps minimum + weight shift between them.

## Sequencing rule of thumb (30 fps)

anticipation : action : settle ≈ 2 : 1 : 2 in frames. Fast actions keep the
action phase 3-6 frames regardless of total length. Between two successive
actions insert a 6-12 frame "moving hold" (micro-drift 1-2cm, never frozen).

## Verification loop (always)

1. `viewport_screenshot` at every key frame — silhouette readable? knees over
   toes? no interpenetration?
2. `get_transforms` on Foot points at all keys — XZ identical while planted?
3. Sample mid-interval transforms for arcs.
4. `keyframes(action="list")` — no accidental keys on wrong frames.
