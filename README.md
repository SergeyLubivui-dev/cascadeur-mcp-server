# Cascadeur MCP Server (Pro)

**Drive [Cascadeur](https://cascadeur.com) straight from an AI assistant.** This is a deep [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that lets Claude — or any MCP client — rig characters, pose and keyframe animations, retarget motion between skeletons, run Cascadeur's AI/physics helpers, and export Unity‑ready FBX clips, all by talking to a live Cascadeur session.

> ⭐ **If this saves you time, please [star the repo](https://github.com/SergeyLubivui-dev/cascadeur-mcp-server) — it's the #1 thing that keeps the project moving.** Stars help other animators find it and tell me which features to build next.

[![Star on GitHub](https://img.shields.io/github/stars/SergeyLubivui-dev/cascadeur-mcp-server?style=social)](https://github.com/SergeyLubivui-dev/cascadeur-mcp-server)

---

## Why this exists

Cascadeur is a phenomenal physics‑based animation tool, but everything happens by hand in the UI. This server exposes Cascadeur's Python API as **58 clean, battle‑tested MCP tools** so an AI agent can do the repetitive, fiddly, or math‑heavy parts for you: auto‑rig a Mixamo model, block a walk cycle, retarget a clip onto a different skeleton without twisting the legs, physics‑fill the in‑betweens, and spit out separate Unity animation clips.

It's inspired by [ysk424/cascadeur-mcp](https://github.com/ysk424/cascadeur-mcp) but goes far deeper: instead of a single `exec(code)` call, you get a registry of verified operations, batching, hot‑reload, full one‑command auto‑rigging, a cross‑skeleton retargeter, and an in‑app **Tools Pro** menu.

**Keywords / topics:** `cascadeur` · `mcp` · `model-context-protocol` · `claude` · `ai-animation` · `auto-rig` · `mixamo` · `retargeting` · `fbx` · `bvh` · `unity` · `3d-animation` · `character-rigging` · `motion-retargeting` · `inverse-kinematics` · `python` · `animation-pipeline` · `game-dev` · `anthropic` · `llm-tools`

---

## Highlights

- 🦴 **One‑command auto‑rig** — import a Mixamo/UE5/CC/AccuRig FBX and get a full Cascadeur rig with controllers in ~15 seconds.
- 🎬 **No‑twist retargeting** — transfer a whole animation onto another character by joint **name** or canonical **role** (transfers rotations + hip‑scaled root, so different bone lengths don't stretch).
- 🧲 **AI + physics fill** — spline (Bézier), IK/fulcrum foot planting, and Cascadeur's physics **attractor** ("tween machine") to fill in‑betweens.
- 📦 **Unity export without the paid FBX license** — a built‑in baker writes ASCII FBX 7.3 / BVH, and can split a timeline into **separate `Model@clip.fbx` clips** (walk / sit / idle) instead of one merged take.
- 🧰 **Tools Pro in‑app menu** — the same actions as clickable commands inside Cascadeur, no coding required.
- ⚡ **Batching + hot‑reload** — many ops per call; edit the bridge and it reloads without restarting Cascadeur.

---

## Architecture

```
MCP client (Claude Code / Claude Desktop / any MCP host)
   │  stdio
   ▼
cascadeur-mcp-pro   (FastMCP — src/cascadeur_mcp_pro/server.py)   ── 58 tools
   │  TCP 127.0.0.1:53621   (port advertised in %TEMP%\cascadeur_mcp_pro.json)
   ▼  trigger: cascadeur.exe --run-script commands.mcp_bridge.exec_bridge
Bridge inside Cascadeur   (commands/mcp_bridge/, runs on the main thread)
   └─ op registry: scene.* objects.* transform.* keys.* fbx.* tool.* rig.* anim.* ai.*
```

- **One tool call = one short bridge session.** Inside a session you can run a whole batch of ops (`cascadeur_batch`).
- **Hot reload:** `_impl.py` and the op modules reload on each trigger, so bridge edits apply without restarting Cascadeur (call `install_bridge.py` after editing).
- **Tools Pro** commands live in `commands/tools_pro/` and call the *same* ops **in‑process** — no TCP — so one implementation powers both the AI automation and the in‑app buttons.

---

## Install

```powershell
cd D:\claude-SB\MCP_Cascadeur
uv venv .venv
uv pip install -e .
python install_bridge.py     # copies the bridge + Tools Pro into <Cascadeur>/resources/scripts/python/commands/
```

Register with Claude Code (an `.mcp.json` is included), or:

```powershell
claude mcp add cascadeur -e CASCADEUR_EXE_PATH=F:\0_Main\cascadeur.exe -- D:\claude-SB\MCP_Cascadeur\.venv\Scripts\cascadeur-mcp-pro.exe
```

Cascadeur must be running (GUI). After `install_bridge.py`, use **Reload commands** in Cascadeur (or restart) to pick up the Tools Pro menu.

---

## Tool reference (58 tools)

Every tool returns JSON. Groups below note how tools **chain together** in a real workflow.

### Connection & meta
| Tool | What it does |
|---|---|
| `cascadeur_status` | Check the bridge connection, latency, and a scene summary. Start here. |
| `health_check` | Deeper self‑test of the bridge + rig readiness. |
| `cascadeur_run_python` | Escape hatch: run raw Python inside Cascadeur (`csc`, `scene`, `app`, `pycsc` in scope). |
| `cascadeur_api_search` | Search Cascadeur's Python API (`api_document.py`, `pycsc`, samples) — **use before writing `cascadeur_run_python`**. |
| `cascadeur_batch` | Run many ops in one bridge session (fastest way to script a build). |
| `cascadeur_action` | Call any official action id (e.g. `Scene.Undo`, `Timeline.Change to IK key`). |

### Scene, camera & I/O
| Tool | What it does |
|---|---|
| `scene_info` | Current character, frame count, open tabs, selection. |
| `scene_manage` | new / open / save / close_tab / set_frame / **set_clip_length**. |
| `cleanup_tabs` | Close extra scene tabs to free memory (Cascadeur bloats fast with leaked tabs). |
| `set_camera` | Aim the viewport (front/back/side/top/¾) at a target — do this before screenshots. |
| `viewport_screenshot` | Render the viewport to a PNG (renders after the session returns; the server waits for the file). |
| `import_fbx` | Import a model / scene / animation FBX. |
| `export_fbx` | Native Cascadeur FBX export (**paid license** — see gotchas). |
| `add_prop`, `add_chair` | Drop a **static** cube/sphere/chair prop for the character to interact with. |

### Objects & selection
`list_objects` · `get_hierarchy` · `select_objects` · `get_selection` — inspect the scene graph and drive selection (needed by some actions).

### Rigging
| Tool | What it does |
|---|---|
| `auto_rig` ★ | **Full one‑shot rig** from a QRT template: rig‑mode on → load template → generate elements → rig‑mode off. |
| `rig_templates` | List available `.qrigcasc` templates (Mixamo / UE5 / CC3 / standard …). |
| `bone_map` | Classify **any** skeleton's joints into canonical roles (hips, thigh_l, foot_r, hand_l, fingers…) and link each to its controller points. **Call this before posing** — address bones by role, never hardcoded names. |
| `rig_info`, `rig_joints`, `rig_mode`, `quick_rig_tool`, `rig_reach` | Rig introspection, mode toggling, and reach limits (never place an IK target past ~95 % of a chain). |

★ For a Mixamo character: `import_fbx(mode="model", new_scene=True)` → `bone_map()` → `auto_rig("Mixamo_Namespace_Template_New")`.

### Posing & transforms
| Tool | What it does |
|---|---|
| `get_transforms` / `set_transforms` | Read/write controller **positions & rotations**. `set_transforms` routes to the point's `Position` input node, keys the track, and re‑solves the rig (IK runs). |
| `apply_local_transforms` | Set full **local** transforms (pos + rot + scale) per joint in FK — the no‑twist way to transfer a pose. |
| `block_pose` | Block a key pose with a few defining controllers (feet + hips + intent) and let AutoPosing complete the body. |
| `pose_apply`, `transfer_pose` | Apply a saved/dataset pose, or copy a pose from another scene/frame. |

### Animation & keyframes
| Tool | What it does |
|---|---|
| `tracks` | List/inspect timeline tracks (layers). |
| `keyframes` | list / set / delete keys. |
| `set_interval` | Set interpolation (**BEZIER**/LINEAR/STEP/FIXED), kinematics (**IK/FK/GR**), and **fulcrum** foot fixation per section. |
| `bake_keys` | Key every frame — turns sampled data into a real baked animation (prerequisite for `auto_interpolate` and clean export). |
| `set_kinematics` | Switch IK/FK/GR at a frame or over an interval. |
| `animate_sequence`, `quick_animate` | Orchestrate a pose‑to‑pose blocking + spline pass. |
| `mirror` | Mirror a pose/frame left↔right. |

### Retargeting (transfer animation between rigs)
| Tool | What it does |
|---|---|
| `retarget_full` | Bake a whole clip and re‑apply it onto a target by **full local transforms** — clean, no IK twist. Best for same‑family skeletons. |
| `retarget_animation` | Cross‑rig retarget: match bones by **name** or canonical **role**, transfer rotations, and scale the root by hip‑height ratio (so a tall rig's stride fits a short one). |
| `motion_retarget` | Point/position‑based retarget (legacy path). |

### AI & physics (local, works on the free license)
| Tool | What it does |
|---|---|
| `auto_pose_update` | Run the ML AutoPosing update on the current frame. |
| `auto_interpolate` | Editable‑Animation / auto‑interpolation "spline" pass (best‑effort headless). |
| `physics_tween` | Cascadeur's physics **attractor** ("tween machine") — physically‑plausible in‑betweens (Inertial / Average / Interpolation …). |
| `auto_physics` | Toggle the AutoPhysics tool. |
| `physics_snap`, `ballistic_trajectory`, `add_jump_arc` | Physics snapping, ballistic arcs, jump trajectories. |
| `root_motion` | Cascadeur's generative Root Motion over an interval. |
| `foot_lock`, `add_secondary_motion` | Lock planted feet (no sliding); add lag/overshoot follow‑through. |

### Export (no paid license needed)
| Tool | What it does |
|---|---|
| `export_animation` ★ | **Built‑in baker** → ASCII FBX 7.3 / BVH / JSON. Skeleton + baked curves that retarget by joint name — the classic Mixamo/Unity clip workflow, no paid FBX export required. |

★ Pair with `bake_keys` for clean per‑frame curves, and split into per‑clip files for Unity (see Tools Pro → Export to Unity).

### Reference dataset
`dataset_capture` · `dataset_list` · `dataset_pose` — capture normalized motion/pose records (role‑keyed world positions + local rotations + foot contacts) and reapply them onto any rigged character.

---

## Tools Pro — in‑app menu (no coding)

After `install_bridge.py`, Cascadeur's command list gains a **Tools Pro** submenu (assign a hotkey to *Open Panel*). These run the same ops in‑process:

| Command | Action |
|---|---|
| **Open Panel** | A button window with all actions below. |
| **Rig Mixamo FBX** | Pick an FBX → import → auto bone‑map → Quick Rig → animatable (non‑interactive, no "Generate rig" popup). |
| **Retarget animation from FBX** | Pick a source clip → auto name/role match → apply onto the current character. |
| **Physics fill in‑betweens** | Spline (Bézier) + feet IK/fulcrum + physics attractor. |
| **Export to Unity** | Enter clips (`walk:0-30, sit:30-70`) → separate `Model@clip.fbx` files. |

---

## Animation‑craft skill

`.claude/skills/animation-craft/` teaches the agent the **12 principles of animation** mapped to concrete MCP operations, plus humanoid balance/IK constraints, timing tables, and pose recipes (sit, stand, walk, jump). It loads automatically before animation tasks so poses come out physically plausible.

---

## Typical workflow

```text
# 1. Rig a Mixamo character
import_fbx  path=".../MtbBiker2.fbx"  mode="model"  new_scene=true
bone_map
auto_rig    template="Mixamo_Namespace_Template_New"

# 2. Retarget a walk onto it (name/role match, no twist)
retarget_animation  source=".../walk.fbx"

# 3. Fill + polish
bake_keys
set_interval  frame=0  interpolation="BEZIER"
physics_tween frame=10 mode="Interpolation"

# 4. Verify + export Unity clips
set_camera         preset="3q"  target=[0,90,0]
viewport_screenshot
export_animation   path="D:/out/hero@walk.fbx"  format="fbx"
```

`set_transforms` finds the correct input node automatically: on a rig point that's the `Position` data node (while `Transform.global_position` is a computed *output*), then it keys the object's track and re‑runs the rig update so IK solves.

---

## Known gotchas (learned the hard way)

1. **Quick Rig outside rig mode = crash.** `create_from_qrt_by_fileName` / `generate_rig_elements` hard‑crash Cascadeur unless the scene is in rig mode. `auto_rig` always enters it first.
2. **Native FBX export is a paid feature.** Free/trial writes only `.casc` (the error is only in the event log). Use `export_animation` (the built‑in baker) instead.
3. **Clip length** isn't `set_animation_size`; it's a section on the default layer + `fit_animation_size_by_layers` (handled by `scene_manage set_clip_length`).
4. **`scene.save()` returns False even on success** — the tools verify via the filesystem.
5. **Screenshots render asynchronously** after the bridge session returns to Qt's event loop — the server waits for the file.
6. **Leaked scene tabs bloat memory** and can wipe undo history — use `cleanup_tabs`.
7. **AI Inbetweening (ML) is unusable on the free license** (produces NaN) — use `physics_tween` + Bézier instead.

---

## Development

- Edit `cascadeur_side/mcp_bridge/**` → `python install_bridge.py` → changes apply immediately (hot‑reload; no Cascadeur restart).
- Edit `cascadeur_side/tools_pro/**` → `python install_bridge.py` → then **Reload commands** in Cascadeur.
- Quick test without the MCP layer: `.venv\Scripts\python test_bridge.py scene.info` or `test_bridge.py --batch-file batch.json`.
- API reference: the `cascadeur_api_search` tool searches `api_document.py`, `pycsc`, `samples`, `rig_mode`, `prototypes`.

---

## Support the project

This is built and maintained in the open. If it's useful:

- ⭐ **[Star the repo](https://github.com/SergeyLubivui-dev/cascadeur-mcp-server)** — seriously, it helps a lot.
- 🐛 Open an issue with bugs, skeletons that don't map, or feature requests.
- 🔧 PRs welcome — new QRT templates, exporters, and AI passes especially.

Made for animators who'd rather direct than click. Built on Cascadeur's `csc` API; not affiliated with Nekki.
