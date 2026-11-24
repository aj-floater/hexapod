# Body CAD — Handoff for a FreeCAD MCP chat

> Written 2026-11-23. Part 1 is for Archie (getting the MCP link working). Part 2 is the brief for the Claude Code agent that drafts the body geometry. Open a new chat at the repo root and point it at this file.

---

## Part 1 — Getting FreeCAD MCP working (Archie's steps)

What is already in place (checked 2026-11-23):
- **MCP server:** `freecad` is configured in Claude Code (user scope). It runs `uv --directory ~/Coding/freecad-mcp run freecad-mcp` (neka-nat/freecad-mcp v0.1.32).
- **FreeCAD addon:** `FreeCADMCP` is installed in the flatpak FreeCAD 1.1.1 (`~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/FreeCADMCP`).
- **Flatpak permissions:** network is shared (so the RPC on `localhost:9875` is reachable from the host) and the host filesystem is visible (so it can open repo files).
- **What's missing:** the RPC server inside FreeCAD isn't running. Nothing was listening on port 9875.

Steps:
1. Start FreeCAD: `flatpak run org.freecad.FreeCAD` (or from the app menu).
2. Switch to the **MCP Addon** workbench (workbench dropdown).
3. Click **Start RPC Server** in the **FreeCAD MCP** toolbar.
4. Optional: in the **FreeCAD MCP** menu, tick **Auto-Start Server** so it starts with FreeCAD from now on.
5. Check it's listening: `ss -ltn | grep 9875`.
6. Open a **new** Claude Code chat in `/home/arjames/Coding/hexapod`. Run `/mcp` and check that `freecad` shows as connected. If it says failed, restart the chat after step 3: the MCP server only connects once FreeCAD's RPC is up.
7. Paste: *"Read `hardware/body_board/BODY_CAD_HANDOFF.md` Part 2 and start."*

Troubleshooting:
- **Tool calls error with "connection refused":** the RPC server isn't running (repeat step 3) or FreeCAD was restarted without Auto-Start.
- **Screenshots come back black:** see `~/Coding/freecad-mcp/docs/configuration.md` (screenshot fallback). Or ask the agent to work text-only with `get_objects`, and check the view yourself.
- **Updating the MCP server:** `cd ~/Coding/freecad-mcp && git pull`. The addon copy in the flatpak Mod folder must be updated to match: re-copy `addon/FreeCADMCP`.

---

## Part 2 — Brief for the body CAD agent

> **Read `BODY_CAD_UPDATE_01_compact_stance.md` as well.** It overrides this brief where they conflict: narrow and low stance, smallest and lightest possible body.

**Audience:** a Claude Code agent with the `freecad` MCP tools (`get_objects`, `create_object`, `execute_code`, `get_view`, and others).

### Goal
Draft a **first-pass hexapod body** in FreeCAD. It must hold the battery, the body PCB and the six legs. Its main job is to **pin down the numbers the body PCB layout needs**:
- PCB outline and mounting holes
- leg connector positions and exit directions
- harness lengths
- where the battery, USB-C, buttons, OLED and receiver sit

It is a draft for discussion. Keep it **parametric** (one Spreadsheet of key dimensions driving the sketches) so Archie can change leg spacing or PCB size and everything follows.

### Ask Archie first (short multiple choice)
1. **Leg layout:** a rectangle with 3 legs per side (classic, wider middle legs optional) or a hexagonal/radial layout? What leg spacing and body size is he picturing?
2. **Construction:** a 3D printed (PLA?) top and bottom plate with standoffs, or a printed tub with a lid? Printer bed size?
3. **PCB as structure:** is the body PCB a structural plate (legs bolt to it) or just mounted inside the shell?
4. **Battery:** 2× 18650 side by side or end to end; a printed holder or a bought holder; removable or fixed?
5. **Stance:** ground clearance and nominal standing pose (body height), to check leg reach and harness routing.
6. **Existing references:** any sketches, photos or gen-1 dimensions (gen 1 was Arduino Mega + 18× MG996R; there's a photo at `docs/report/figures/firstgen.png`)?

### Inputs in the repo (treat as read-only)
| File | Use |
|---|---|
| `hardware/CAD/LegAssembly.FCStd` | Leg assembly: 3× MG90D, **octagonal base joint** (coxa yaw), `PCB Cover`, embedded smart_servo_v2 model. The body must take the coxa mount from this. |
| `hardware/CAD/Parts.FCStd` | Individual leg parts |
| `hardware/smart_servo_v2/smart_servo_v2.step` | Leg board, 59.6 × 27.2 mm (lives inside the leg housing, not the body) |
| `hardware/body_board/SPEC.md` | What the body PCB contains (§2 block diagram, §5 connectors) |
| `docs/report/report.tex` | Leg mechanical design and kinematics. Link lengths **36 / 62 / 87 mm** (coxa/femur/tibia). |

**Never save over `LegAssembly.FCStd` or `Parts.FCStd`.** Create a new document `hardware/CAD/Body.FCStd`, and bring legs in with `App::Link` (or a copied shape) for fit checks. The working tree has unrelated uncommitted changes, so **do not commit**.

### What the body has to hold
| Item | Size / constraint |
|---|---|
| 2× 18650 (2S) | Ø18.4 × 65 mm bare (protected cells ~67–70 mm), ~47 g each. Near the centre of mass, low down. Balance leads to the PCB. |
| Body PCB | Outline TBD by you: propose an envelope (a starting guess is ~90 × 110 mm, but derive it from the layout). Needs M3 mounting holes. 4 or 2 layers, 1.6 mm. |
| 6× leg connector (JST-XH 4-pin, 2.5 mm, vertical) | On the PCB edge nearest each leg. The harness runs **through the coxa yaw joint**, so leave a slack loop and strain relief. Record the harness length per leg. |
| USB-C (charge + PC data) | Reachable from outside with the legs attached |
| POWER button and MOTORS OFF button | Reachable from outside. MOTORS OFF should be easy to hit fast (top of the body). |
| OLED module | 0.96–1.3" SSD1306 module (~27 × 27 mm board; check a real module). Window in the top. |
| ELRS receiver | Small (~10–20 mm). Antenna(s) out, away from the battery and motors. |
| IMU (on the PCB) | Near the body centre. Just mark the spot. |

### Deliverables
1. `hardware/CAD/Body.FCStd`: a parametric draft body with the legs linked in at their stance pose.
2. `hardware/body_board/research/body_geometry.md`, the hand-back to the body PCB work. It must contain:
   - the PCB outline (dimensions, plus a DXF exported to `hardware/body_board/research/body_pcb_outline.dxf` for KiCad Edge.Cuts import)
   - mounting hole positions and sizes
   - **a table of the 6 leg connectors**: (x, y) on the PCB, the exit direction, and the harness length to each leg's J4
   - positions for USB-C, the buttons, the OLED and the receiver
   - keep-outs (battery, standoffs) and height limits above and below the PCB
3. A short list of open mechanical questions.

### Working tips
- Start with `get_objects` / `list_documents` and look at the leg assembly before building anything.
- Use `execute_code` for parametric scripts; keep them simple, with `# Section Name` headers (Archie's preference).
- Save often. FreeCAD writes `.FCBak` backups next to the file.
- Archie prefers to do simple GUI steps himself. Ask him rather than fighting the GUI through code.
