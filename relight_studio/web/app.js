/**
 * RELIGHT STUDIO — RS-PRODUCT-1.1
 * Studio Workspace Client Application
 * Authoritative 3D interaction engine, real-time gizmo manipulation,
 * dual-viewport rendering, dynamic preview quality, and photographic control.
 */

// Application State
const state = {
  selectedId: "light_01",
  displayMode: "relit",
  overlayOpacity: 0.6,
  splitRatio: 0.5,
  isDraggingSplit: false,
  
  // Photograph Viewport Pan/Zoom
  photoZoom: 1.0,
  photoPan: { x: 0, y: 0 },
  isPanningPhoto: false,
  lastMousePhoto: { x: 0, y: 0 },
  
  // 3D Stage Viewport Orbit/Pan/Interaction
  stageOrbit: { yaw: 35.0, pitch: 25.0, dist: 3.8 },
  isOrbitingStage: false,
  isPanningStage: false,
  lastMouseStage: { x: 0, y: 0 },
  mouseDownPos: { x: 0, y: 0 },
  
  // Interactive 3D Gizmo & Picking
  projectionMeta: null,
  alignmentMeta: null,
  activeGizmoAxis: null,
  hoverGizmoAxis: null,
  hoverTarget: null,
  isDraggingGizmo: false,
  isInteracting: false,
  
  // Cached Viewport Images
  photoImg: new Image(),
  origImg: new Image(),
  stageImg: new Image(),
  
  // Debounce & Progressive Timer
  sliderDebounceTimer: null,
  dragThrottleTimer: null
};

// DOM References
const photoCanvas = document.getElementById("photo-canvas");
const photoCtx = photoCanvas.getContext("2d");
const photoContainer = document.getElementById("photo-canvas-container");
const splitSliderLine = document.getElementById("split-slider-line");

const stageCanvas = document.getElementById("stage-canvas");
const stageCtx = stageCanvas.getContext("2d");
const stageContainer = document.getElementById("stage-canvas-container");

const hierarchyTree = document.getElementById("hierarchy-tree");
const inspectorContent = document.getElementById("inspector-content");
const inspectorTargetType = document.getElementById("inspector-target-type");

const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");
const telemetryGpuMs = document.getElementById("telemetry-gpu-ms");
const telemetryWallMs = document.getElementById("telemetry-wall-ms");
const telemetryFps = document.getElementById("telemetry-fps");
const orbitInfo = document.getElementById("orbit-info");
const photoDimensions = document.getElementById("photo-dimensions");
const zoomLevelText = document.getElementById("zoom-level-text");

const modalProject = document.getElementById("modal-project");

// --------------------------------------------------------------------------
// 1. INITIALIZATION & RESIZE
// --------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  setupEventHandlers();
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has("view")) {
    state.displayMode = urlParams.get("view");
    const sel = document.getElementById("select-display-mode");
    if (sel) sel.value = state.displayMode;
  }
  if (urlParams.has("alpha")) {
    state.overlayOpacity = parseFloat(urlParams.get("alpha"));
    const slider = document.getElementById("slider-overlay-opacity");
    if (slider) slider.value = state.overlayOpacity;
  }
  resizeCanvases();
  window.addEventListener("resize", resizeCanvases);
  refreshAll();
});

function resizeCanvases() {
  if (photoContainer && photoCanvas) {
    photoCanvas.width = photoContainer.clientWidth;
    photoCanvas.height = photoContainer.clientHeight;
  }
  if (stageContainer && stageCanvas) {
    stageCanvas.width = stageContainer.clientWidth;
    stageCanvas.height = stageContainer.clientHeight;
  }
  renderPhotoViewport();
  renderStageViewport();
}

// --------------------------------------------------------------------------
// 2. BACKEND API CALLS & REFRESH
// --------------------------------------------------------------------------
async function refreshAll() {
  try {
    setStatus("rendering", "Rendering Preview...");
    const res = await fetch("/api/state/full");
    const data = await res.json();
    
    state.selectedId = data.selected_id;
    updateTelemetry(data.telemetry);
    renderHierarchy(data.hierarchy);
    renderInspector(data.inspector);
    
    // Fetch 3D Stage & Photograph Viewport Alignment Meta
    fetchProjectionMeta();
    fetchAlignmentMeta();

    // Update Photograph image stream with current display mode & opacity
    refreshPhotoStream();
    
    if (data.orig_image_url) {
      state.origImg.src = data.orig_image_url + "?t=" + Date.now();
    }
    
    // Update Stage image
    if (data.stage_image_url) {
      state.stageImg.onload = () => renderStageViewport();
      state.stageImg.src = data.stage_image_url + "?t=" + Date.now();
    }
    
    if (data.is_missing_assets && data.missing_assets && data.missing_assets.length > 0) {
      setStatus("error", `MISSING ASSETS: ${data.missing_assets.join(', ')}`);
    } else {
      setStatus("ready", "Engine Ready");
    }
  } catch (err) {
    console.error("Refresh failed:", err);
    setStatus("ready", "Ready");
  }
}

function refreshPhotoStream() {
  state.photoImg.onload = () => {
    photoDimensions.textContent = `${state.photoImg.naturalWidth} x ${state.photoImg.naturalHeight}`;
    renderPhotoViewport();
  };
  state.photoImg.src = `/api/images/photo?mode=${encodeURIComponent(state.displayMode)}&opacity=${state.overlayOpacity}&t=${Date.now()}`;
}

async function fetchProjectionMeta() {
  try {
    const res = await fetch("/api/stage/projection_meta?width=640&height=480");
    state.projectionMeta = await res.json();
  } catch (err) {
    console.error("Failed to fetch projection meta:", err);
  }
}

async function fetchAlignmentMeta() {
  try {
    const res = await fetch("/api/camera/alignment_meta");
    state.alignmentMeta = await res.json();
  } catch (err) {
    console.error("Failed to fetch alignment meta:", err);
  }
}

function setStatus(type, msg) {
  if (!statusPill || !statusText) return;
  statusPill.className = `status-pill ${type}`;
  statusText.textContent = msg;
}

function updateTelemetry(t) {
  if (!t) return;
  if (t.gpu_time_ms !== undefined) telemetryGpuMs.textContent = `${t.gpu_time_ms.toFixed(2)} ms`;
  if (t.wall_time_ms !== undefined) telemetryWallMs.textContent = `${t.wall_time_ms.toFixed(2)} ms`;
  if (t.fps !== undefined) telemetryFps.textContent = `${t.fps.toFixed(1)} FPS`;
}

// --------------------------------------------------------------------------
// 3. PHOTOGRAPH VIEWPORT RENDERING (REGION A)
// --------------------------------------------------------------------------
function renderPhotoViewport() {
  if (!photoCtx || !state.photoImg.complete || !state.photoImg.naturalWidth) return;
  
  const W = photoCanvas.width;
  const H = photoCanvas.height;
  photoCtx.clearRect(0, 0, W, H);
  
  // Background checkboard for transparency inspection
  drawCheckerboard(photoCtx, W, H);
  
  const imgW = state.photoImg.naturalWidth;
  const imgH = state.photoImg.naturalHeight;
  
  photoCtx.save();
  // Apply Zoom & Pan
  photoCtx.translate(W / 2 + state.photoPan.x, H / 2 + state.photoPan.y);
  photoCtx.scale(state.photoZoom, state.photoZoom);
  photoCtx.translate(-imgW / 2, -imgH / 2);
  
  if (state.displayMode === "split" && state.origImg.complete && state.origImg.naturalWidth) {
    // Left: Original Photograph
    const splitX = imgW * state.splitRatio;
    photoCtx.save();
    photoCtx.beginPath();
    photoCtx.rect(0, 0, splitX, imgH);
    photoCtx.clip();
    photoCtx.drawImage(state.origImg, 0, 0);
    photoCtx.restore();
    
    // Right: Relit Photograph
    photoCtx.save();
    photoCtx.beginPath();
    photoCtx.rect(splitX, 0, imgW - splitX, imgH);
    photoCtx.clip();
    photoCtx.drawImage(state.photoImg, 0, 0);
    photoCtx.restore();
    
    // Split dividing line
    photoCtx.strokeStyle = "#ffffff";
    photoCtx.lineWidth = 2 / state.photoZoom;
    photoCtx.beginPath();
    photoCtx.moveTo(splitX, 0);
    photoCtx.lineTo(splitX, imgH);
    photoCtx.stroke();
  } else if (state.displayMode === "original" && state.origImg.complete) {
    photoCtx.drawImage(state.origImg, 0, 0);
  } else {
    photoCtx.drawImage(state.photoImg, 0, 0);
  }
  
  photoCtx.restore();
  
  // Update split slider DOM handle position
  if (state.displayMode === "split") {
    splitSliderLine.style.display = "block";
    const screenSplitX = W / 2 + state.photoPan.x + (state.splitRatio - 0.5) * (imgW * state.photoZoom);
    splitSliderLine.style.left = `${screenSplitX}px`;
  } else {
    splitSliderLine.style.display = "none";
  }
}

function drawCheckerboard(ctx, w, h) {
  const size = 16;
  ctx.fillStyle = "#111113";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#161619";
  for (let y = 0; y < h; y += size) {
    for (let x = (y / size % 2) * size; x < w; x += size * 2) {
      ctx.fillRect(x, y, size, size);
    }
  }
}

// --------------------------------------------------------------------------
// 4. 3D VIRTUAL STUDIO STAGE VIEWPORT (REGION B)
// --------------------------------------------------------------------------
function renderStageViewport() {
  if (!stageCtx || !state.stageImg.complete || !state.stageImg.naturalWidth) return;
  const W = stageCanvas.width;
  const H = stageCanvas.height;
  stageCtx.clearRect(0, 0, W, H);
  
  // Fit stage image onto canvas preserving aspect ratio
  const imgW = state.stageImg.naturalWidth;
  const imgH = state.stageImg.naturalHeight;
  const scale = Math.min(W / imgW, H / imgH);
  const dw = imgW * scale;
  const dh = imgH * scale;
  const dx = (W - dw) / 2;
  const dy = (H - dh) / 2;
  
  stageCtx.drawImage(state.stageImg, dx, dy, dw, dh);

  // Draw Interactive Gizmo Axis Highlight if hovering/dragging
  if (state.projectionMeta && state.projectionMeta.gizmo) {
    const g = state.projectionMeta.gizmo;
    const ax = state.activeGizmoAxis || state.hoverGizmoAxis;
    if (ax) {
      stageCtx.save();
      stageCtx.lineWidth = 3.5;
      const c = toCanvasCoords(g.center[0], g.center[1], dx, dy, scale);

      if (ax === "X" && g.axis_x) {
        const p = toCanvasCoords(g.axis_x[0], g.axis_x[1], dx, dy, scale);
        stageCtx.strokeStyle = "#ff4444";
        stageCtx.beginPath();
        stageCtx.moveTo(c.x, c.y);
        stageCtx.lineTo(p.x, p.y);
        stageCtx.stroke();
        stageCtx.fillStyle = "#ff4444";
        stageCtx.beginPath();
        stageCtx.arc(p.x, p.y, 6, 0, Math.PI * 2);
        stageCtx.fill();
      } else if (ax === "Y" && g.axis_y) {
        const p = toCanvasCoords(g.axis_y[0], g.axis_y[1], dx, dy, scale);
        stageCtx.strokeStyle = "#44ff44";
        stageCtx.beginPath();
        stageCtx.moveTo(c.x, c.y);
        stageCtx.lineTo(p.x, p.y);
        stageCtx.stroke();
        stageCtx.fillStyle = "#44ff44";
        stageCtx.beginPath();
        stageCtx.arc(p.x, p.y, 6, 0, Math.PI * 2);
        stageCtx.fill();
      } else if (ax === "Z" && g.axis_z) {
        const p = toCanvasCoords(g.axis_z[0], g.axis_z[1], dx, dy, scale);
        stageCtx.strokeStyle = "#4488ff";
        stageCtx.beginPath();
        stageCtx.moveTo(c.x, c.y);
        stageCtx.lineTo(p.x, p.y);
        stageCtx.stroke();
        stageCtx.fillStyle = "#4488ff";
        stageCtx.beginPath();
        stageCtx.arc(p.x, p.y, 6, 0, Math.PI * 2);
        stageCtx.fill();
      } else if (ax === "PITCH" && g.rot_pitch) {
        const p = toCanvasCoords(g.rot_pitch[0], g.rot_pitch[1], dx, dy, scale);
        stageCtx.strokeStyle = "#f59e0b";
        stageCtx.fillStyle = "#f59e0b";
        stageCtx.beginPath();
        stageCtx.arc(p.x, p.y, 7, 0, Math.PI * 2);
        stageCtx.stroke();
        stageCtx.fill();
      } else if (ax === "YAW" && g.rot_yaw) {
        const p = toCanvasCoords(g.rot_yaw[0], g.rot_yaw[1], dx, dy, scale);
        stageCtx.strokeStyle = "#06b6d4";
        stageCtx.fillStyle = "#06b6d4";
        stageCtx.beginPath();
        stageCtx.arc(p.x, p.y, 7, 0, Math.PI * 2);
        stageCtx.stroke();
        stageCtx.fill();
      } else if (ax === "ROLL" && g.rot_roll) {
        const p = toCanvasCoords(g.rot_roll[0], g.rot_roll[1], dx, dy, scale);
        stageCtx.strokeStyle = "#ec4899";
        stageCtx.fillStyle = "#ec4899";
        stageCtx.beginPath();
        stageCtx.arc(p.x, p.y, 7, 0, Math.PI * 2);
        stageCtx.stroke();
        stageCtx.fill();
      } else if (ax === "SCALE" && g.scale_uniform) {
        const p = toCanvasCoords(g.scale_uniform[0], g.scale_uniform[1], dx, dy, scale);
        stageCtx.strokeStyle = "#ffffff";
        stageCtx.fillStyle = "#ffffff";
        stageCtx.beginPath();
        stageCtx.arc(p.x, p.y, 7, 0, Math.PI * 2);
        stageCtx.stroke();
        stageCtx.fill();
      }
      stageCtx.restore();
    }
  }

  orbitInfo.textContent = `Yaw: ${state.stageOrbit.yaw.toFixed(0)}° | Pitch: ${state.stageOrbit.pitch.toFixed(0)}°`;
}

function toCanvasCoords(ix, iy, dx, dy, scale) {
  return { x: dx + ix * scale, y: dy + iy * scale };
}

function toImageCoords(cx, cy) {
  if (!state.stageImg.naturalWidth) return { ix: 0, iy: 0, inside: false };
  const W = stageCanvas.width;
  const H = stageCanvas.height;
  const imgW = state.stageImg.naturalWidth;
  const imgH = state.stageImg.naturalHeight;
  const scale = Math.min(W / imgW, H / imgH);
  const dw = imgW * scale;
  const dh = imgH * scale;
  const dx = (W - dw) / 2;
  const dy = (H - dh) / 2;

  const ix = (cx - dx) / scale;
  const iy = (cy - dy) / scale;
  const inside = (cx >= dx && cx <= dx + dw && cy >= dy && cy <= dy + dh);
  return { ix, iy, inside, scale };
}

function distToSegment(px, py, ax, ay, bx, by) {
  const l2 = (bx - ax) * (bx - ax) + (by - ay) * (by - ay);
  if (l2 === 0) return Math.hypot(px - ax, py - ay);
  let t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)));
}

function hitTestStage(cx, cy) {
  if (!state.projectionMeta) return { type: "none" };
  const { ix, iy, inside } = toImageCoords(cx, cy);
  if (!inside) return { type: "none" };

  const meta = state.projectionMeta;

  // 1. Gizmo handles for selected light or subject
  if (meta.gizmo) {
    const g = meta.gizmo;
    const tol = 16.0;

    // Pitch ring handle
    if (g.rot_pitch && Math.hypot(ix - g.rot_pitch[0], iy - g.rot_pitch[1]) < tol) {
      return { type: "gizmo", axis: "PITCH" };
    }
    // Yaw ring handle
    if (g.rot_yaw && Math.hypot(ix - g.rot_yaw[0], iy - g.rot_yaw[1]) < tol) {
      return { type: "gizmo", axis: "YAW" };
    }
    // Roll ring handle
    if (g.rot_roll && Math.hypot(ix - g.rot_roll[0], iy - g.rot_roll[1]) < tol) {
      return { type: "gizmo", axis: "ROLL" };
    }
    // Scale uniform handle
    if (g.scale_uniform && Math.hypot(ix - g.scale_uniform[0], iy - g.scale_uniform[1]) < tol) {
      return { type: "gizmo", axis: "SCALE" };
    }
    // Axis X
    if (g.axis_x && distToSegment(ix, iy, g.center[0], g.center[1], g.axis_x[0], g.axis_x[1]) < tol * 0.8) {
      return { type: "gizmo", axis: "X" };
    }
    // Axis Y
    if (g.axis_y && distToSegment(ix, iy, g.center[0], g.center[1], g.axis_y[0], g.axis_y[1]) < tol * 0.8) {
      return { type: "gizmo", axis: "Y" };
    }
    // Axis Z
    if (g.axis_z && distToSegment(ix, iy, g.center[0], g.center[1], g.axis_z[0], g.axis_z[1]) < tol * 0.8) {
      return { type: "gizmo", axis: "Z" };
    }
    // Center handle
    if (g.center && Math.hypot(ix - g.center[0], iy - g.center[1]) < tol) {
      return { type: "gizmo", axis: "X" };
    }
  }

  // 2. Lights in scene
  if (meta.lights) {
    for (const l of meta.lights) {
      if (l.center && Math.hypot(ix - l.center[0], iy - l.center[1]) < 22.0) {
        return { type: "light", id: l.id };
      }
    }
  }

  // 3. Subject proxy
  if (meta.subject && meta.subject.visible && meta.subject.center) {
    if (Math.hypot(ix - meta.subject.center[0], iy - meta.subject.center[1]) < 28.0) {
      return { type: "subject", id: "subject" };
    }
  }

  return { type: "none" };
}

// --------------------------------------------------------------------------
// 5. SCENE HIERARCHY RENDERING (REGION C)
// --------------------------------------------------------------------------
function renderHierarchy(treeData) {
  if (!hierarchyTree || !treeData || !treeData.scene) return;
  hierarchyTree.innerHTML = "";
  
  const root = treeData.scene;
  
  function createNode(item) {
    if (item.type === "group") {
      const groupHeader = document.createElement("div");
      groupHeader.className = "tree-group-title";
      groupHeader.textContent = item.name;
      hierarchyTree.appendChild(groupHeader);
      
      if (item.children) {
        item.children.forEach(child => hierarchyTree.appendChild(createNode(child)));
      }
      return document.createDocumentFragment();
    }
    
    const node = document.createElement("div");
    node.className = `tree-node ${item.id === state.selectedId ? "selected" : ""}`;
    node.dataset.id = item.id;
    
    const left = document.createElement("div");
    left.className = "tree-node-left";
    
    let iconSvg = '<svg class="tree-node-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>';
    if (item.type === "light") {
      iconSvg = '<svg class="tree-node-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>';
    } else if (item.type === "camera") {
      iconSvg = '<svg class="tree-node-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>';
    } else if (item.type === "subject") {
      iconSvg = '<svg class="tree-node-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>';
    }
    
    left.innerHTML = `${iconSvg}<span>${item.name}</span>`;
    node.appendChild(left);
    
    if (item.type === "light") {
      const actions = document.createElement("div");
      actions.className = "tree-node-actions";
      
      const toggle = document.createElement("span");
      toggle.className = "tree-node-toggle";
      toggle.title = item.enabled ? "Disable Light" : "Enable Light";
      toggle.innerHTML = item.enabled
        ? '<svg class="icon-small" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
        : '<svg class="icon-small" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
      
      toggle.addEventListener("click", async (e) => {
        e.stopPropagation();
        await fetch(`/api/light/toggle?id=${item.id}`, { method: "POST" });
        refreshAll();
      });
      
      actions.appendChild(toggle);
      node.appendChild(actions);
    }
    
    node.addEventListener("click", () => {
      selectObject(item.id);
    });
    
    return node;
  }
  
  if (root.children) {
    root.children.forEach(child => hierarchyTree.appendChild(createNode(child)));
  }
}

async function selectObject(id) {
  state.selectedId = id;
  await fetch(`/api/select?id=${id}`, { method: "POST" });
  refreshAll();
}

// --------------------------------------------------------------------------
// 6. CONTEXT INSPECTOR RENDERING (REGION D)
// --------------------------------------------------------------------------
function renderInspector(data) {
  if (!inspectorContent || !data) return;
  inspectorContent.innerHTML = "";
  inspectorTargetType.textContent = (data.type || "SCENE").toUpperCase();
  
  if (data.type === "light") {
    renderLightInspector(data);
  } else if (data.type === "subject") {
    renderMaterialInspector(data);
  } else if (data.type === "environment") {
    renderEnvironmentInspector(data);
  } else if (data.type === "receiver") {
    renderReceiverInspector(data);
  } else if (data.type === "camera") {
    renderCameraInspector(data);
  }
}

function renderLightInspector(light) {
  // 1. Lighting Starter Presets
  const secPreset = createSection("Photographic Lighting Presets");
  const grid = document.createElement("div");
  grid.className = "preset-grid";
  const presets = [
    { label: "Key Softbox", id: "key_softbox" },
    { label: "Fill Softbox", id: "fill_softbox" },
    { label: "Rim Strip", id: "rim_strip" },
    { label: "Top Softbox", id: "top_light" },
    { label: "Side Rake", id: "side_light" }
  ];
  presets.forEach(p => {
    const btn = document.createElement("button");
    btn.className = "btn-light-preset";
    btn.textContent = p.label;
    btn.addEventListener("click", async () => {
      await fetch("/api/light/preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset: p.id, id: light.id })
      });
      refreshAll();
    });
    grid.appendChild(btn);
  });
  secPreset.appendChild(grid);
  inspectorContent.appendChild(secPreset);

  // 2. Identity
  const secName = createSection("Identity");
  secName.appendChild(createTextInputRow("Name", light.name, (val) => {
    dispatchMutation("/api/light/update", { id: light.id, name: val });
  }));
  inspectorContent.appendChild(secName);
  
  // 3. 3D Transform & Dimensions
  const secTransform = createSection("3D Transform & Size");
  secTransform.appendChild(createSliderRow("Pos X (m)", -3.0, 3.0, 0.05, light.position[0], (v) => {
    light.position[0] = v;
    dispatchMutation("/api/light/transform", { id: light.id, pos: light.position });
  }));
  secTransform.appendChild(createSliderRow("Pos Y (m)", 0.0, 4.0, 0.05, light.position[1], (v) => {
    light.position[1] = v;
    dispatchMutation("/api/light/transform", { id: light.id, pos: light.position });
  }));
  secTransform.appendChild(createSliderRow("Pos Z (m)", -3.0, 4.0, 0.05, light.position[2], (v) => {
    light.position[2] = v;
    dispatchMutation("/api/light/transform", { id: light.id, pos: light.position });
  }));
  secTransform.appendChild(createSliderRow("Pitch (°)", -90.0, 90.0, 1.0, light.rotation_deg[0], (v) => {
    light.rotation_deg[0] = v;
    dispatchMutation("/api/light/transform", { id: light.id, rot_deg: light.rotation_deg });
  }));
  secTransform.appendChild(createSliderRow("Yaw (°)", -180.0, 180.0, 1.0, light.rotation_deg[1], (v) => {
    light.rotation_deg[1] = v;
    dispatchMutation("/api/light/transform", { id: light.id, rot_deg: light.rotation_deg });
  }));
  secTransform.appendChild(createSliderRow("Width (m)", 0.1, 2.5, 0.05, light.width, (v) => {
    dispatchMutation("/api/light/transform", { id: light.id, width: v });
  }));
  secTransform.appendChild(createSliderRow("Height (m)", 0.1, 2.5, 0.05, light.height, (v) => {
    dispatchMutation("/api/light/transform", { id: light.id, height: v });
  }));
  inspectorContent.appendChild(secTransform);
  
  // 4. Photometric Emission
  const secEmission = createSection("Photometric Emission");
  secEmission.appendChild(createSliderRow("Intensity", 0.0, 5.0, 0.05, light.intensity, (v) => {
    dispatchMutation("/api/light/properties", { id: light.id, intensity: v });
  }));
  secEmission.appendChild(createSliderRow("Kelvin (K)", 2000.0, 9000.0, 100.0, light.temperature_kelvin, (v) => {
    dispatchMutation("/api/light/properties", { id: light.id, temperature_kelvin: v });
  }));
  secEmission.appendChild(createSelectRow("Convention", ["FIXED_RADIANCE", "FIXED_POWER"], light.energy_convention, (v) => {
    dispatchMutation("/api/light/properties", { id: light.id, energy_convention: v });
  }));
  secEmission.appendChild(createCheckboxRow("Cast Shadows", light.cast_shadows, (v) => {
    dispatchMutation("/api/light/properties", { id: light.id, cast_shadows: v });
  }));
  secEmission.appendChild(createCheckboxRow("Light Enabled", light.enabled, (v) => {
    dispatchMutation("/api/light/properties", { id: light.id, enabled: v });
  }));
  inspectorContent.appendChild(secEmission);
}

function renderMaterialInspector(subj) {
  // 1. Subject Approximate 3D Geometry & Alignment
  const secProxy = createSection("Proxy Geometry & 3D Alignment");
  secProxy.appendChild(createSelectRow("Proxy Type", ["OBB", "SUPERQUADRIC", "SPHERE"], subj.proxy_type || "OBB", (v) => {
    dispatchMutation("/api/subject/params", { proxy_type: v });
  }));

  // Snap to Floor button
  const snapBtn = document.createElement("button");
  snapBtn.className = "btn-action-primary";
  snapBtn.textContent = "Snap Proxy to Floor";
  snapBtn.addEventListener("click", async () => {
    await fetch("/api/subject/snap_ground", { method: "POST" });
    refreshAll();
  });
  secProxy.appendChild(snapBtn);

  // Ground Contact Status
  const gapM = subj.ground_gap_m !== undefined ? subj.ground_gap_m : 0.0;
  const cState = subj.contact_state || "contact";
  const contactRow = document.createElement("div");
  contactRow.className = "inspector-row two-col";
  contactRow.innerHTML = `<span class="inspector-label">Ground Gap:</span><span class="diag-val ${cState === 'contact' ? 'good' : 'warn'}">${gapM.toFixed(3)}m (${cState.toUpperCase()})</span>`;
  secProxy.appendChild(contactRow);

  // Alignment Diagnostics Box
  if (state.alignmentMeta && state.alignmentMeta.diagnostics) {
    const d = state.alignmentMeta.diagnostics;
    const diagBox = document.createElement("div");
    diagBox.className = "alignment-diag-box";
    const iouPct = (d.silhouette_iou * 100).toFixed(1);
    const covPct = (d.foreground_coverage * 100).toFixed(1);
    diagBox.innerHTML = `
      <div class="diag-row"><span class="diag-label">Silhouette IoU:</span><span class="diag-val ${d.silhouette_iou > 0.5 ? 'good' : 'warn'}">${iouPct}%</span></div>
      <div class="diag-row"><span class="diag-label">FG Coverage:</span><span class="diag-val ${d.foreground_coverage > 0.6 ? 'good' : 'warn'}">${covPct}%</span></div>
      <div class="diag-row"><span class="diag-label">BBox Delta:</span><span class="diag-val">[${(d.bbox_delta_px || []).join(', ')}] px</span></div>
    `;
    secProxy.appendChild(diagBox);
  }

  // 3D Position
  const pos = subj.position || [0.0, subj.position_y || 0.35, 0.0];
  secProxy.appendChild(createSliderRow("Pos X (m)", -3.0, 3.0, 0.05, pos[0], (v) => {
    pos[0] = v;
    dispatchMutation("/api/subject/params", { position: pos });
  }));
  secProxy.appendChild(createSliderRow("Pos Y (m)", -1.0, 3.0, 0.05, pos[1], (v) => {
    pos[1] = v;
    dispatchMutation("/api/subject/params", { position: pos, position_y: v });
  }));
  secProxy.appendChild(createSliderRow("Pos Z (m)", -3.0, 3.0, 0.05, pos[2], (v) => {
    pos[2] = v;
    dispatchMutation("/api/subject/params", { position: pos });
  }));

  // 3D Rotation (Pitch, Yaw, Roll)
  const rot = subj.rotation_deg || [0.0, 0.0, 0.0];
  secProxy.appendChild(createSliderRow("Pitch (°)", -180.0, 180.0, 5.0, rot[0], (v) => {
    rot[0] = v;
    dispatchMutation("/api/subject/params", { rotation_deg: rot });
  }));
  secProxy.appendChild(createSliderRow("Yaw (°)", -180.0, 180.0, 5.0, rot[1], (v) => {
    rot[1] = v;
    dispatchMutation("/api/subject/params", { rotation_deg: rot });
  }));
  secProxy.appendChild(createSliderRow("Roll (°)", -180.0, 180.0, 5.0, rot[2], (v) => {
    rot[2] = v;
    dispatchMutation("/api/subject/params", { rotation_deg: rot });
  }));

  // Dimensions
  const dims = subj.dimensions || [0.35, 0.35, 0.35];
  secProxy.appendChild(createSliderRow("Width (m)", 0.05, 3.0, 0.05, dims[0], (v) => {
    dims[0] = v;
    dispatchMutation("/api/subject/params", { dimensions: dims });
  }));
  secProxy.appendChild(createSliderRow("Height (m)", 0.05, 3.0, 0.05, dims[1], (v) => {
    dims[1] = v;
    dispatchMutation("/api/subject/params", { dimensions: dims });
  }));
  secProxy.appendChild(createSliderRow("Depth (m)", 0.05, 3.0, 0.05, dims[2], (v) => {
    dims[2] = v;
    dispatchMutation("/api/subject/params", { dimensions: dims });
  }));
  inspectorContent.appendChild(secProxy);

  // 2. PBR Material Profile
  const secProfile = createSection("PBR Material Profile");
  secProfile.appendChild(createSelectRow("Preset", ["Custom", "Fabric", "Marble", "Plastic", "Rough Metal", "Polished Metal"], "Custom", (v) => {
    dispatchMutation("/api/material/profile", { profile: v });
  }));
  inspectorContent.appendChild(secProfile);
  
  // 3. Microfacet BRDF
  const secProps = createSection("Microfacet BRDF");
  secProps.appendChild(createSliderRow("Roughness", 0.04, 1.0, 0.02, subj.roughness, (v) => {
    dispatchMutation("/api/material/params", { roughness: v });
  }));
  secProps.appendChild(createSliderRow("Metallic", 0.0, 1.0, 0.05, subj.metallic, (v) => {
    dispatchMutation("/api/material/params", { metallic: v });
  }));
  secProps.appendChild(createSliderRow("Specular F0", 0.0, 0.20, 0.01, subj.specular_f0, (v) => {
    dispatchMutation("/api/material/params", { specular_f0: v });
  }));
  secProps.appendChild(createSliderRow("Intensity", 0.0, 3.0, 0.1, subj.specular_intensity, (v) => {
    dispatchMutation("/api/material/params", { specular_intensity: v });
  }));
  secProps.appendChild(createCheckboxRow("Enable Specular", subj.enable_specular, (v) => {
    dispatchMutation("/api/material/params", { enable_specular: v });
  }));
  inspectorContent.appendChild(secProps);
}

function renderEnvironmentInspector(env) {
  const secEnv = createSection("Image-Based Lighting (IBL)");
  secEnv.appendChild(createCheckboxRow("Enable IBL", env.enabled, (v) => {
    dispatchMutation("/api/environment/params", { enabled: v });
  }));
  secEnv.appendChild(createSliderRow("Intensity", 0.0, 5.0, 0.1, env.intensity, (v) => {
    dispatchMutation("/api/environment/params", { intensity: v });
  }));
  secEnv.appendChild(createSliderRow("Rotation (°)", 0.0, 360.0, 5.0, env.rotation_deg, (v) => {
    dispatchMutation("/api/environment/params", { rotation_deg: v });
  }));
  secEnv.appendChild(createSliderRow("Diffuse Wt", 0.0, 1.0, 0.05, env.diffuse_weight, (v) => {
    dispatchMutation("/api/environment/params", { diffuse_weight: v });
  }));
  secEnv.appendChild(createSliderRow("Specular Wt", 0.0, 1.0, 0.05, env.specular_weight, (v) => {
    dispatchMutation("/api/environment/params", { specular_weight: v });
  }));
  inspectorContent.appendChild(secEnv);
}

function renderReceiverInspector(rec) {
  const secRec = createSection("Background Receiver");
  secRec.appendChild(createSelectRow("Type", ["CYCLORAMA", "PLANE"], rec.receiver_type, (v) => {
    dispatchMutation("/api/receiver/params", { receiver_type: v });
  }));
  secRec.appendChild(createSliderRow("Ground Y (m)", -1.0, 1.0, 0.05, rec.ground_y, (v) => {
    dispatchMutation("/api/receiver/params", { receiver_type: rec.receiver_type, ground_y: v });
  }));
  secRec.appendChild(createSliderRow("Cove Radius (m)", 0.05, 2.0, 0.05, rec.cove_radius, (v) => {
    dispatchMutation("/api/receiver/params", { receiver_type: rec.receiver_type, cove_radius: v });
  }));
  secRec.appendChild(createSliderRow("Wall Z (m)", -4.0, 0.0, 0.1, rec.wall_z !== undefined ? rec.wall_z : -1.2, (v) => {
    dispatchMutation("/api/receiver/params", { receiver_type: rec.receiver_type, wall_z: v });
  }));
  inspectorContent.appendChild(secRec);
}

function renderCameraInspector(cam) {
  // 1. Lens Focal Length Presets
  const secPreset = createSection("35mm Equivalent Lens Presets");
  const grid = document.createElement("div");
  grid.className = "lens-preset-grid";
  const presets = [
    { label: "24mm", id: "24mm" },
    { label: "35mm", id: "35mm" },
    { label: "50mm", id: "50mm" },
    { label: "85mm", id: "85mm" },
    { label: "105mm", id: "105mm" }
  ];
  presets.forEach(p => {
    const btn = document.createElement("button");
    const isActive = Math.abs((cam.focal_length_mm || 50.0) - parseFloat(p.id)) < 2.0;
    btn.className = `btn-lens-preset ${isActive ? 'active' : ''}`;
    btn.textContent = p.label;
    btn.addEventListener("click", async () => {
      await fetch("/api/camera/preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset: p.id })
      });
      refreshAll();
    });
    grid.appendChild(btn);
  });
  secPreset.appendChild(grid);
  inspectorContent.appendChild(secPreset);

  // 2. Optical Parameters
  const secOptics = createSection("Optical Matching");
  const curFl = cam.focal_length_mm || 50.0;
  secOptics.appendChild(createSliderRow("Focal (mm)", 18.0, 200.0, 1.0, curFl, (v) => {
    dispatchMutation("/api/camera/params", { focal_length_mm: v });
  }));
  secOptics.appendChild(createSliderRow("FOV (°)", 10.0, 90.0, 1.0, cam.fov_deg, (v) => {
    dispatchMutation("/api/camera/params", { fov_deg: v });
  }));
  inspectorContent.appendChild(secOptics);

  // 3. Perspective & Framing
  const secPose = createSection("Perspective & Framing");
  const curDist = cam.distance || 3.0;
  secPose.appendChild(createSliderRow("Distance (m)", 0.5, 10.0, 0.1, curDist, (v) => {
    dispatchMutation("/api/camera/params", { distance: v });
  }));
  const curElev = cam.elevation || (cam.pos ? cam.pos[1] : 1.2);
  secPose.appendChild(createSliderRow("Elevation (m)", -2.0, 4.0, 0.1, curElev, (v) => {
    dispatchMutation("/api/camera/params", { elevation: v });
  }));

  // Framing buttons
  const fitBtn = document.createElement("button");
  fitBtn.className = "btn-action-primary";
  fitBtn.textContent = "Fit Frame to Subject";
  fitBtn.addEventListener("click", async () => {
    await fetch("/api/camera/fit", { method: "POST" });
    refreshAll();
  });
  secPose.appendChild(fitBtn);

  const resetBtn = document.createElement("button");
  resetBtn.className = "btn-subtle";
  resetBtn.style.marginTop = "6px";
  resetBtn.textContent = "Reset to 50mm Normal";
  resetBtn.addEventListener("click", async () => {
    await fetch("/api/camera/reset", { method: "POST" });
    refreshAll();
  });
  secPose.appendChild(resetBtn);

  inspectorContent.appendChild(secPose);
}

// --------------------------------------------------------------------------
// UI WIDGET HELPERS
// --------------------------------------------------------------------------
function createSection(title) {
  const sec = document.createElement("div");
  sec.className = "inspector-section";
  const h = document.createElement("div");
  h.className = "inspector-section-title";
  h.textContent = title;
  sec.appendChild(h);
  return sec;
}

function createSliderRow(label, min, max, step, val, onChange) {
  const row = document.createElement("div");
  row.className = "inspector-row";
  
  const lbl = document.createElement("span");
  lbl.className = "inspector-label";
  lbl.textContent = label;
  
  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = min;
  slider.max = max;
  slider.step = step;
  slider.value = val;
  
  const num = document.createElement("input");
  num.type = "text";
  num.className = "val-input";
  num.value = Number(val).toFixed(step < 1 ? 2 : 0);
  
  slider.addEventListener("mousedown", () => {
    fetch("/api/interaction/begin", { method: "POST" });
  });

  slider.addEventListener("input", () => {
    num.value = Number(slider.value).toFixed(step < 1 ? 2 : 0);
    debounceMutation(() => onChange(parseFloat(slider.value)));
  });

  slider.addEventListener("mouseup", () => {
    fetch("/api/interaction/end", { method: "POST" });
    refreshAll();
  });
  
  num.addEventListener("change", () => {
    slider.value = num.value;
    onChange(parseFloat(num.value));
  });
  
  row.appendChild(lbl);
  row.appendChild(slider);
  row.appendChild(num);
  return row;
}

function createTextInputRow(label, val, onChange) {
  const row = document.createElement("div");
  row.className = "inspector-row two-col";
  const lbl = document.createElement("span");
  lbl.className = "inspector-label";
  lbl.textContent = label;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "text-input";
  input.value = val;
  input.addEventListener("change", () => onChange(input.value));
  row.appendChild(lbl);
  row.appendChild(input);
  return row;
}

function createSelectRow(label, options, selectedVal, onChange) {
  const row = document.createElement("div");
  row.className = "inspector-row two-col";
  const lbl = document.createElement("span");
  lbl.className = "inspector-label";
  lbl.textContent = label;
  const select = document.createElement("select");
  select.className = "select-input";
  options.forEach(opt => {
    const o = document.createElement("option");
    o.value = opt;
    o.textContent = opt;
    if (opt === selectedVal) o.selected = true;
    select.appendChild(o);
  });
  select.addEventListener("change", () => onChange(select.value));
  row.appendChild(lbl);
  row.appendChild(select);
  return row;
}

function createCheckboxRow(label, checked, onChange) {
  const row = document.createElement("div");
  row.className = "inspector-row two-col";
  const lbl = document.createElement("span");
  lbl.className = "inspector-label";
  lbl.textContent = label;
  const wrap = document.createElement("label");
  wrap.className = "checkbox-wrap";
  const chk = document.createElement("input");
  chk.type = "checkbox";
  chk.checked = !!checked;
  chk.addEventListener("change", () => onChange(chk.checked));
  wrap.appendChild(chk);
  row.appendChild(lbl);
  row.appendChild(wrap);
  return row;
}

function debounceMutation(fn) {
  clearTimeout(state.sliderDebounceTimer);
  state.sliderDebounceTimer = setTimeout(fn, 15);
}

async function dispatchMutation(url, body) {
  try {
    setStatus("rendering", "Updating...");
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (data.telemetry) updateTelemetry(data.telemetry);
    refreshAll();
  } catch (err) {
    console.error("Mutation failed:", err);
  }
}

// --------------------------------------------------------------------------
// 7. EVENT HANDLERS & 3D INTERACTION
// --------------------------------------------------------------------------
function setupEventHandlers() {
  // Split Slider Wipe Drag
  splitSliderLine.addEventListener("mousedown", (e) => {
    state.isDraggingSplit = true;
    e.preventDefault();
  });
  
  window.addEventListener("mouseup", () => {
    if (state.isDraggingGizmo) {
      state.isDraggingGizmo = false;
      state.activeGizmoAxis = null;
      fetch("/api/interaction/end", { method: "POST" });
      refreshAll();
    }
    state.isDraggingSplit = false;
    state.isPanningPhoto = false;
    state.isOrbitingStage = false;
    state.isPanningStage = false;
  });
  
  window.addEventListener("mousemove", (e) => {
    if (state.isDraggingSplit) {
      const rect = photoContainer.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      state.splitRatio = x / rect.width;
      renderPhotoViewport();
    }
  });
  
  // Photo Viewport Pan & Zoom
  photoCanvas.addEventListener("mousedown", (e) => {
    if (e.button === 0) {
      state.isPanningPhoto = true;
      state.lastMousePhoto = { x: e.clientX, y: e.clientY };
    }
  });
  
  photoCanvas.addEventListener("mousemove", (e) => {
    if (state.isPanningPhoto) {
      const dx = e.clientX - state.lastMousePhoto.x;
      const dy = e.clientY - state.lastMousePhoto.y;
      state.photoPan.x += dx;
      state.photoPan.y += dy;
      state.lastMousePhoto = { x: e.clientX, y: e.clientY };
      renderPhotoViewport();
    }
  });
  
  photoCanvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    state.photoZoom = Math.max(0.1, Math.min(5.0, state.photoZoom * factor));
    zoomLevelText.textContent = `${Math.round(state.photoZoom * 100)}%`;
    renderPhotoViewport();
  }, { passive: false });
  
  document.getElementById("btn-zoom-fit").addEventListener("click", () => {
    state.photoZoom = 1.0;
    state.photoPan = { x: 0, y: 0 };
    zoomLevelText.textContent = "100%";
    renderPhotoViewport();
  });
  
  document.getElementById("btn-zoom-100").addEventListener("click", () => {
    state.photoZoom = 1.0;
    zoomLevelText.textContent = "100%";
    renderPhotoViewport();
  });
  
  document.getElementById("select-display-mode").addEventListener("change", (e) => {
    state.displayMode = e.target.value;
    refreshPhotoStream();
  });

  const sliderOpacity = document.getElementById("slider-overlay-opacity");
  if (sliderOpacity) {
    sliderOpacity.addEventListener("input", (e) => {
      state.overlayOpacity = parseFloat(e.target.value);
      refreshPhotoStream();
    });
  }
  
  // 3D Stage Viewport: Hit-Testing, Gizmo Dragging, Orbit & Pan
  stageCanvas.addEventListener("mousedown", (e) => {
    const rect = stageCanvas.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    state.mouseDownPos = { x: cx, y: cy };
    state.lastMouseStage = { x: cx, y: cy };

    const hit = hitTestStage(cx, cy);

    if (hit.type === "gizmo") {
      state.activeGizmoAxis = hit.axis;
      state.isDraggingGizmo = true;
      fetch("/api/interaction/begin", { method: "POST" });
      renderStageViewport();
      return;
    } else if (hit.type === "light") {
      selectObject(hit.id);
      return;
    } else if (hit.type === "subject") {
      selectObject("subject");
      return;
    }

    // Otherwise orbit or pan stage camera
    if (e.shiftKey || e.button === 1) {
      state.isPanningStage = true;
    } else {
      state.isOrbitingStage = true;
    }
  });
  
  stageCanvas.addEventListener("mousemove", (e) => {
    const rect = stageCanvas.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;

    if (state.isDraggingGizmo && state.activeGizmoAxis) {
      const dx = cx - state.lastMouseStage.x;
      const dy = cy - state.lastMouseStage.y;
      state.lastMouseStage = { x: cx, y: cy };

      // Map canvas pixels to projection image space
      const { scale } = toImageCoords(cx, cy);
      const scaledDx = dx / (scale || 1.0);
      const scaledDy = dy / (scale || 1.0);

      // Perform real-time drag mutation
      fetch("/api/stage/drag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          axis: state.activeGizmoAxis,
          dx: scaledDx,
          dy: scaledDy,
          width: 640,
          height: 480
        })
      }).then(() => {
        // Fast-path reload stage and relit buffers
        state.stageImg.src = "/api/images/stage?t=" + Date.now();
        refreshPhotoStream();
      });
      return;
    }

    if (state.isOrbitingStage) {
      const dx = cx - state.lastMouseStage.x;
      const dy = cy - state.lastMouseStage.y;
      state.stageOrbit.yaw += dx * 0.5;
      state.stageOrbit.pitch = Math.max(-85, Math.min(85, state.stageOrbit.pitch + dy * 0.5));
      state.lastMouseStage = { x: cx, y: cy };
      
      debounceMutation(async () => {
        await fetch(`/api/stage/orbit?yaw=${state.stageOrbit.yaw}&pitch=${state.stageOrbit.pitch}`, { method: "POST" });
        state.stageImg.src = "/api/images/stage?t=" + Date.now();
        fetchProjectionMeta();
      });
      return;
    }

    if (state.isPanningStage) {
      const dx = (cx - state.lastMouseStage.x) * 0.005;
      const dy = (cy - state.lastMouseStage.y) * 0.005;
      state.lastMouseStage = { x: cx, y: cy };

      debounceMutation(async () => {
        await fetch(`/api/stage/orbit?pan_x=${dx}&pan_y=${dy}`, { method: "POST" });
        state.stageImg.src = "/api/images/stage?t=" + Date.now();
        fetchProjectionMeta();
      });
      return;
    }

    // Hover hit-testing and cursor feedback
    const hit = hitTestStage(cx, cy);
    if (hit.type === "gizmo") {
      stageCanvas.style.cursor = "grab";
      state.hoverGizmoAxis = hit.axis;
    } else if (hit.type === "light" || hit.type === "subject") {
      stageCanvas.style.cursor = "pointer";
      state.hoverGizmoAxis = null;
    } else {
      stageCanvas.style.cursor = "default";
      state.hoverGizmoAxis = null;
    }
    renderStageViewport();
  });
  
  stageCanvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 0.9 : 1.1;
    state.stageOrbit.dist = Math.max(1.0, Math.min(10.0, state.stageOrbit.dist * factor));
    debounceMutation(async () => {
      await fetch(`/api/stage/orbit?dist=${state.stageOrbit.dist}`, { method: "POST" });
      state.stageImg.src = "/api/images/stage?t=" + Date.now();
      fetchProjectionMeta();
    });
  }, { passive: false });
  
  document.getElementById("btn-focus-stage-cam").addEventListener("click", async () => {
    await fetch("/api/stage/focus", { method: "POST" });
    refreshAll();
  });

  document.getElementById("btn-reset-stage-cam").addEventListener("click", async () => {
    await fetch("/api/stage/reset", { method: "POST" });
    refreshAll();
  });
  
  // Toolbar Buttons
  document.getElementById("btn-undo").addEventListener("click", async () => {
    await fetch("/api/undo", { method: "POST" });
    refreshAll();
  });
  
  document.getElementById("btn-redo").addEventListener("click", async () => {
    await fetch("/api/redo", { method: "POST" });
    refreshAll();
  });
  
  document.getElementById("btn-add-light").addEventListener("click", async () => {
    await fetch("/api/light/add", { method: "POST" });
    refreshAll();
  });
  
  document.getElementById("btn-dup-light").addEventListener("click", async () => {
    await fetch("/api/light/duplicate", { method: "POST" });
    refreshAll();
  });
  
  document.getElementById("btn-del-light").addEventListener("click", async () => {
    await fetch("/api/light/delete", { method: "POST" });
    refreshAll();
  });
  
  document.getElementById("select-backend").addEventListener("change", async (e) => {
    const isMetal = e.target.value === "metal";
    await fetch(`/api/backend?use_metal=${isMetal}`, { method: "POST" });
    refreshAll();
  });
  
  document.getElementById("btn-render-final").addEventListener("click", async () => {
    setStatus("rendering", "Rendering Final Quality (32 MC)...");
    await fetch("/api/render/final", { method: "POST" });
    refreshAll();
  });
  
  document.getElementById("btn-save-proj").addEventListener("click", async () => {
    const res = await fetch("/api/project/save", { method: "POST" });
    const data = await res.json();
    alert(`Saved project bundle: ${data.path}`);
  });
  
  document.getElementById("btn-export-img").addEventListener("click", async () => {
    const res = await fetch("/api/project/export", { method: "POST" });
    const data = await res.json();
    alert(`Exported relit photograph: ${data.path}`);
  });
  
  // Modal handlers
  document.getElementById("btn-new-proj").addEventListener("click", () => modalProject.showModal());
  document.getElementById("btn-import-photo").addEventListener("click", () => modalProject.showModal());
  document.getElementById("btn-modal-close").addEventListener("click", () => modalProject.close());
  document.getElementById("btn-modal-cancel").addEventListener("click", () => modalProject.close());
  
  document.querySelectorAll(".btn-preset").forEach(btn => {
    btn.addEventListener("click", () => {
      document.getElementById("input-photo-path").value = btn.dataset.path;
    });
  });
  
  document.getElementById("btn-modal-confirm").addEventListener("click", async () => {
    const name = document.getElementById("input-proj-name").value;
    const path = document.getElementById("input-photo-path").value;
    await fetch(`/api/project/new`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, image_path: path })
    });
    modalProject.close();
    refreshAll();
  });
  
  // Keyboard Shortcuts (Cmd+Z, Cmd+Shift+Z)
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "z") {
      e.preventDefault();
      if (e.shiftKey) {
        document.getElementById("btn-redo").click();
      } else {
        document.getElementById("btn-undo").click();
      }
    }
  });
}
