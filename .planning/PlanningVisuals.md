# PlanningVisuals

## Summary
- Use `referral files/dumb stuff 3.py` only as the behavior reference for two prototype features: the 3-frame walking animation and the pairwise exposure heat map.
- Rebuild those visuals only inside BRIGID’s RTLS Dashboard, not in other BRIGID modules.
- Keep the simulation and visual controls frontend-owned, with one small backend payload addition so the dashboard receives an ordered room polygon for clipping and bot containment.
- Implement for the currently active RTLS room now, but keep the geometry helpers ready to expand to multi-room later.

## Prompt Draft
```text
Study `referral files/dumb stuff 3.py` as the source-of-truth prototype for two behaviors only: (1) the 3-frame walking animation driven by heading and speed, and (2) the pairwise exposure heat map whose sensitivity increases exposure radius. Do not port the PyQt6 UI. Rebuild those behaviors inside BRIGID’s existing React/Electron RTLS Dashboard only.

Implement the visuals in the current RTLS dashboard canvas and its module-local right panel. The heat map must stay strictly clipped inside the active room region of the floor plan and must never bleed into the rest of the panel. Bots are temporary fake tags that coexist with real live RTLS tags. Their motion must run in world space, continue while the user pans or zooms, and never allow a bot center to leave the room polygon. The walking animation uses the three assets in `BRIGID/assets/Walking animation`, applies to bots only in this phase, and must render at a fixed on-screen size so zooming does not scale the sprite. Real tags keep their current dot rendering for now, but both real tags and bots must contribute to the exposure heat map.

Add a new `Visual Settings` section in the RTLS right panel with only these controls: a Heat Map toggle plus Sensitivity slider, a Walking Animation toggle, and a Bots toggle with an `Add Random` button. Add no other settings and do not persist these settings yet. The result should feel like the prototype, but with a higher-resolution heat map, a smoother multi-stop gradient, and responsive pan/zoom with no visible lag.
```

## Key Changes
- Backend payload:
  - Extend room serialization and RTLS snapshot/load responses to include ordered `room_polygon_ft` for the active room in world coordinates.
- Frontend state:
  - Add local `VisualSettings`, `SimBot`, and `VisualEntity` state in `RTLSDashboard.tsx`.
  - Bots stay dashboard-local only; enabling Bots seeds 6 bots if none exist yet, `Add Random` adds 1 more, and disable that button at 24 bots to protect frame rate.
- Canvas/rendering:
  - Refactor `RTLSDashboardCanvas.tsx` to run a `requestAnimationFrame` loop for dynamic visuals while preserving the current pan/zoom behavior.
  - Convert the prototype’s px-based movement and heat constants into world-space once from the room’s reset-view fit scale, then keep simulation zoom-independent after that.
  - Keep bot sprites and bot dots at fixed screen-space size; only their positions follow the world-to-screen transform.
  - Clip both the heat raster and bot sprite draw pass to `room_polygon_ft`; when a proposed bot step exits the room, keep the last valid position and reflect heading against the nearest boundary segment.
  - Build heat from every visible entity pair: connected live tags plus enabled bots. Preserve the prototype’s deposit/decay behavior, upgrade the LUT to a smoother cyan-to-green-to-yellow-to-orange-to-red ramp, and render from a device-pixel-aware offscreen buffer so pan/zoom stays smooth.
- Right panel UI:
  - Add one `Visual Settings` section to the existing RTLS right panel and nothing else.
  - Controls: `Heat Map` toggle, `Sensitivity` slider, `Walking Animation` toggle, `Bots` toggle, `Add Random` button.
  - `Heat Map` off hides only the raster, `Walking Animation` off falls back to fixed bot dots, and `Bots` off hides and pauses bots without clearing the current bot list.

## Public Interfaces
- `RTLSSnapshot` gains `room_polygon_ft: { x: number; y: number }[]`.
- `RTLSDashboardCanvas` gains `roomPolygon`, `visualSettings`, and `simBots` props.
- Add frontend-only types for `VisualSettings`, `SimBot`, and `VisualEntity` for combined live-tag-plus-bot heat calculations.

## Test Plan
- Load a workspace and verify the heat map never renders outside the room polygon after pan, zoom, resize, and reset view.
- Enable Bots and verify all spawned bots start inside the room, keep moving while the user pans/zooms, and never leave the room.
- Zoom in/out and verify bot sprites and bot dots stay the same on-screen size while their world positions stay anchored to the floor plan.
- Toggle Walking Animation on/off and verify bots switch between animated sprites and fixed dots without breaking movement.
- Run live tags with bots enabled and verify both contribute to pairwise exposure heat while real tags remain current dots.
- Increase Sensitivity and verify exposure radius and field size visibly grow without hitching.
- Stress test with 24 bots plus live tags and verify rendering stays smooth and is not tied to the 80 ms polling cadence.

## Assumptions
- The eventual file path is `.planning/PlanningVisuals`, with Markdown-formatted content inside it.
- v1 targets the single active RTLS room, but helper utilities should accept multiple room regions later.
- Walking animation applies only to simulated bots in this phase; live UWB tags keep the current dot/label renderer.
- Visual settings are session-local only and are not written to workspace files or backend config.
