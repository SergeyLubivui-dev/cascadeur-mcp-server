# cascadeur-mcp-pro

Глубокая MCP-интеграция с Cascadeur: сцены, FBX, авто-риггинг по шаблонам
(Mixamo / AccuRig / UE5 / Metahuman...), контроллеры-«ручки», кейфреймы и
интерполяции, скриншоты вьюпорта, поиск по API — всё из Claude/любого MCP-клиента.

Вдохновлён [ysk424/cascadeur-mcp](https://github.com/ysk424/cascadeur-mcp), но
существенно глубже: вместо одного `exec(code)` — реестр из ~30 проверенных
операций внутри Cascadeur, батчинг (много операций за один вызов), hot-reload
моста без перезапуска Cascadeur и полный автоматический риггинг одной командой.

## Архитектура

```
MCP-клиент (Claude Code / Desktop)
   │ stdio
   ▼
cascadeur-mcp-pro (FastMCP, src/cascadeur_mcp_pro/server.py)
   │ TCP 127.0.0.1:53621 (порт в %TEMP%\cascadeur_mcp_pro.json)
   ▼ триггер: cascadeur.exe --run-script commands.mcp_bridge.exec_bridge
Мост внутри Cascadeur (commands/mcp_bridge/, главный поток)
   └─ ops-реестр: scene.* objects.* transform.* keys.* fbx.* tool.* rig.*
```

- Один вызов MCP-инструмента = одна короткая сессия моста; внутри сессии можно
  выполнить пачку операций (`cascadeur_batch`).
- `_impl.py` и ops-модули перезагружаются на каждый триггер — правки моста
  применяются без перезапуска Cascadeur.
- Латентность триггера ~1.5–2 с (форвардинг в запущенный инстанс).

## Установка

```powershell
cd D:\claude-SB\MCP_Cascadeur
uv venv .venv; uv pip install -e .
python install_bridge.py          # копирует мост в <Cascadeur>/resources/scripts/python/commands/
```

Регистрация в Claude Code — файл `.mcp.json` уже в проекте, либо:

```powershell
claude mcp add cascadeur -e CASCADEUR_EXE_PATH=F:\0_Main\cascadeur.exe -- D:\claude-SB\MCP_Cascadeur\.venv\Scripts\cascadeur-mcp-pro.exe
```

Cascadeur должен быть запущен (GUI).

## Инструменты (26)

| Группа | Инструменты |
|---|---|
| Мета | `cascadeur_status`, `cascadeur_run_python`, `cascadeur_api_search`, `cascadeur_batch` |
| Сцена | `scene_info`, `scene_manage` (new/open/save/close_tab/set_frame/set_clip_length) |
| FBX | `import_fbx` (model/scene/animation/...), `export_fbx` (см. лицензию ниже) |
| Объекты | `list_objects`, `get_hierarchy`, `select_objects`, `get_selection` |
| Риг | `auto_rig` ★, `rig_templates`, `rig_info`, `rig_joints`, `rig_mode`, `quick_rig_tool` |
| Позы | `get_transforms`, `set_transforms` (IK-точки, «ручки», джоинты) |
| Анимация | `tracks`, `keyframes` (list/set/delete), `set_interval` (BEZIER/LINEAR/STEP/FIXED, IK/FK, fulcrum) |
| Прочее | `cascadeur_action` (undo/redo/любой action), `mirror`, `viewport_screenshot` |
| Экспорт анимации | `export_animation` ★ — свой бейкер: FBX ASCII 7.3 / BVH / JSON без платной лицензии (скелет+кривые, ретаргет по именам джоинтов) |
| ИИ | `auto_pose_update` — ML-автопозинг на текущем кадре; автопозинг-линки рига работают и сами при `set_transforms` |

Навык постановки поз: `.claude/skills/animation-craft/` — 12 законов анимации,
правила баланса/IK гуманоида, тайминги и рецепты поз (загружается перед
анимационными задачами).

★ `auto_rig` — полный цикл: rig mode on (+Rig info) → шаблон QRT →
генерация элементов → rig mode off → готовый риг с контроллерами. Для
Mixamo-персонажа: `import_fbx(..., mode="model", new_scene=True)` →
`auto_rig("Mixamo_Namespace_Template_New")`. ~15 секунд.

## Типовой сценарий

```
import_fbx path=".../MtbBiker2.fbx" mode="model" new_scene=true
auto_rig template="Mixamo_Namespace_Template_New"
scene_manage action="set_clip_length" frames=40
set_transforms items=[{"name":"mixamorig:LeftHand_MainPoint","global_position":[40,160,25]}] frame=20
set_interval frame=0 interpolation="BEZIER"
viewport_screenshot
scene_manage action="save" path="D:/out/hero.casc"
```

`set_transforms` сам находит правильный входной узел данных: у риг-точек это
data-узел `Position` (а `Transform.global_position` — вычисляемый выход),
ставит ключ на треке объекта и запускает пересчёт рига (IK отрабатывает).

## Важные грабли (выяснено экспериментально)

1. **QRT вне риг-режима = краш Cascadeur.** Методы
   `RiggingToolWindowTool.create_from_qrt_by_fileName` / `generate_rig_elements`
   валят приложение, если сцена не в rig mode. `auto_rig` всегда входит в
   риг-режим сам.
2. **FBX-экспорт — платная функция.** Free/trial лицензия пишет только `.casc`
   (ошибка видна лишь в event log). `export_fbx` теперь честно сообщает об этом.
3. **Длина клипа** меняется не `set_animation_size`, а секцией на default-слое +
   `fit_animation_size_by_layers` (см. `scene.set_clip_length`).
4. **`scene.save()` возвращает False даже при успехе** — проверяем файл.
5. **Скриншоты рендерятся асинхронно** после завершения сессии моста (когда
   главный поток вернётся в Qt event loop) — сервер ждёт файл после закрытия
   сессии.
6. Редкие пропуски триггера `--run-script` — клиент ретраит (3 × 15 с).

## Разработка

- Правки в `cascadeur_side/mcp_bridge/**` → `python install_bridge.py` →
  действуют сразу (hot-reload, Cascadeur не перезапускать).
- Быстрый тест без MCP-слоя: `.venv\Scripts\python test_bridge.py scene.info`
  или `test_bridge.py --batch-file batch.json`.
- Справка по API Cascadeur: инструмент `cascadeur_api_search` (ищет по
  `api_document.py`, `pycsc`, `samples`, `rig_mode`, `prototypes`).
