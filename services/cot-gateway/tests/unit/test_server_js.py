"""T005: JS sensor-flicker spec-review comment (non-executable documentation test).

SPEC REVIEW: Sensor layer flicker on rapid /sites refresh
----------------------------------------------------------
Original issue: When refreshSites() fetched new data and the site or sensor was
momentarily gone (e.g., network delay), the old layers were cleared BEFORE new data
arrived. This caused a visual "flicker" where all rings/icons disappeared for one
frame.

Fix (T006): Move siteLayer.clearLayers() and sensorLayer.clearLayers() to AFTER
`const data = await r.json()` so layers are only cleared if data was received
successfully.

This test module intentionally contains no executable tests — the JS behavior
cannot be exercised directly from Python. The fix is verified by manual browser
inspection and the comment below serves as a permanent specification note.

Example of correct refreshSites() structure:
```js
async function refreshSites() {
  try {
    const r = await fetch('/sites', {cache: 'no-store'});
    if (!r.ok) return;
    const data = await r.json();   // ← data received first

    siteLayer.clearLayers();       // ← then clear layers (no flicker)
    sensorLayer.clearLayers();

    const RING_COLORS = [...];
    // ... render new layers from data ...
  } catch(e) { console.warn('sites fetch err', e); }
}
```
"""

from __future__ import annotations
