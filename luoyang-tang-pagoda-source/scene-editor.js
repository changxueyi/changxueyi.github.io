const DEFAULTS = Object.freeze({
  dayTime: 16.2,
  weather: "sunset",
  towerLights: true,
  windStrength: 0.56,
  cloudSpeed: 0.42,
  waterfallFlow: 1.3,
  bloomStrength: 0.82,
  fogDensity: 0.0072,
  shadows: true,
  grid: false,
  wireframe: false,
  selected: "pagoda",
  hidden: Object.freeze({}),
  transforms: Object.freeze({}),
});

const WEATHER_LABELS = Object.freeze({
  clear: "晴空",
  "cloud-sea": "云海",
  mist: "烟雨迷雾",
  sunset: "盛唐落日",
  moon: "月夜灯火",
});

const WEATHER_PRESETS = Object.freeze({
  clear: Object.freeze({ dayTime: 15.5, fogDensity: 0.014, bloomStrength: 0.72 }),
  "cloud-sea": Object.freeze({ dayTime: 11.2, fogDensity: 0.024, bloomStrength: 0.68 }),
  mist: Object.freeze({ dayTime: 7.15, fogDensity: 0.036, bloomStrength: 0.54 }),
  sunset: Object.freeze({ dayTime: 16.2, fogDensity: 0.0072, bloomStrength: 0.82 }),
  moon: Object.freeze({ dayTime: 22.3, fogDensity: 0.027, bloomStrength: 1.08 }),
});

const SELECTION_LABELS = Object.freeze({
  pagoda: "洛阳古塔",
  pagodaFinial: "鎏金塔刹",
  pagodaBody: "七层塔身",
  pagodaBase: "须弥座台基",
  island: "浮空主岛",
  vegetation: "牡丹与植被",
  dragon: "东方青龙",
  phoenix: "丹穴朱雀",
  cloudsWaterfalls: "云海与瀑布",
});

const listeners = new Set();
const clone = (value) => JSON.parse(JSON.stringify(value));
const clamp = (value, min, max) => Math.min(max, Math.max(min, Number(value) || 0));

let toastTimer = 0;
let sceneApi = null;
let state = {
  ...clone(DEFAULTS),
  hidden: {},
  transforms: {},
};

function byId(id) {
  return document.getElementById(id);
}

function safeCall(name, ...args) {
  const fn = sceneApi && sceneApi[name];
  if (typeof fn === "function") {
    return fn(...args);
  }
  return undefined;
}

function emit(type, detail = {}) {
  const payload = { type, state: clone(state), ...detail };
  listeners.forEach((listener) => {
    try {
      listener(payload);
    } catch (error) {
      console.error("[sceneEditorUI] listener failed", error);
    }
  });
  document.dispatchEvent(new CustomEvent("scene-editor-change", { detail: payload }));
}

function snapshot(patch = {}, type = "state", detail = {}) {
  state = { ...state, ...patch, hidden: { ...(patch.hidden || state.hidden) }, transforms: { ...(patch.transforms || state.transforms) } };
  syncUI();
  emit(type, detail);
  return state;
}

function toast(message) {
  const element = byId("toast");
  if (!element) return;
  element.textContent = message;
  element.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => element.classList.remove("is-visible"), 1900);
}

function formatTime(hour) {
  const totalMinutes = Math.round(clamp(hour, 0, 24) * 60);
  const h = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function setOutput(id, value) {
  const element = byId(`${id}-value`);
  if (element) element.textContent = value;
}

function setPressed(selector, pressed) {
  document.querySelectorAll(selector).forEach((button) => {
    button.setAttribute("aria-pressed", String(pressed));
  });
}

function syncUI() {
  const timeText = formatTime(state.dayTime);
  const time = byId("day-time");
  if (time) time.value = String(state.dayTime);
  setOutput("day-time", timeText);
  const sceneTime = byId("scene-time-readout");
  if (sceneTime) sceneTime.textContent = timeText;

  const weatherValue = byId("weather-value");
  if (weatherValue) weatherValue.textContent = WEATHER_LABELS[state.weather] || state.weather;
  document.querySelectorAll("[data-weather]").forEach((button) => {
    const active = button.dataset.weather === state.weather;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });

  const checks = [
    ["tower-lights", state.towerLights],
    ["shadow-toggle", state.shadows],
  ];
  checks.forEach(([id, checked]) => {
    const input = byId(id);
    if (input) input.checked = Boolean(checked);
  });

  const ranges = [
    ["wind-strength", state.windStrength, 2],
    ["cloud-speed", state.cloudSpeed, 2],
    ["waterfall-flow", state.waterfallFlow, 2],
    ["bloom-strength", state.bloomStrength, 2],
    ["fog-density", state.fogDensity, 3],
  ];
  ranges.forEach(([id, value, digits]) => {
    const input = byId(id);
    if (input) input.value = String(value);
    setOutput(id, Number(value).toFixed(digits));
  });

  const grid = byId("grid-toggle");
  if (grid) grid.setAttribute("aria-pressed", String(state.grid));
  const wireframe = byId("wireframe-toggle");
  if (wireframe) wireframe.setAttribute("aria-pressed", String(state.wireframe));

  const selection = state.selected;
  const selectionName = SELECTION_LABELS[selection] || selection;
  const selectionReadout = byId("selection-name");
  if (selectionReadout) selectionReadout.textContent = selectionName;
  const calloutName = byId("callout-name");
  if (calloutName) calloutName.textContent = selectionName;

  document.querySelectorAll(".tree-row").forEach((row) => {
    const target = row.dataset.target;
    const selected = target === selection;
    row.classList.toggle("is-selected", selected);
    row.setAttribute("aria-selected", String(selected));
    const hidden = Boolean(target && state.hidden[target]);
    row.classList.toggle("is-hidden", hidden);
    const button = row.querySelector(".visibility-button");
    if (button && button.dataset.visibility === target) {
      button.setAttribute("aria-pressed", String(!hidden));
      button.setAttribute("aria-label", `${hidden ? "显示" : "隐藏"}${SELECTION_LABELS[target] || target}`);
    }
  });

  const transform = state.transforms[selection] || {};
  const rx = Number(transform.rx || 0);
  const ry = Number(transform.ry || 0);
  const rz = Number(transform.rz || 0);
  const scale = clamp(transform.scale ?? 1, 0.35, 2.4);
  [
    ["rotate-x", rx, "°"],
    ["rotate-y", ry, "°"],
    ["rotate-z", rz, "°"],
    ["scale-uniform", scale, "×"],
  ].forEach(([id, value, suffix]) => {
    const input = byId(id);
    if (input) input.value = String(value);
    const output = byId(`${id}-value`);
    if (output) output.textContent = `${id === "scale-uniform" ? Number(value).toFixed(2) : Math.round(value)}${suffix}`;
  });
}

function select(target, options = {}) {
  if (!target || !SELECTION_LABELS[target]) return;
  snapshot({ selected: target }, "selection", { selected: target, silent: Boolean(options.silent) });
  safeCall("select", target, options);
}

function toggleVisibility(target) {
  if (!SELECTION_LABELS[target]) return;
  const hidden = { ...state.hidden, [target]: !state.hidden[target] };
  if (!hidden[target]) delete hidden[target];
  snapshot({ hidden }, "visibility", { target, hidden: Boolean(hidden[target]) });
  const visibilityButton = document.querySelector(`[data-visibility="${target}"]`);
  if (visibilityButton) visibilityButton.setAttribute('aria-pressed', String(!hidden[target]));
  safeCall("setVisibility", target, !hidden[target]);
}

function setTransform(axis, value) {
  const selection = state.selected;
  const current = state.transforms[selection] || {};
  const transforms = { ...state.transforms, [selection]: { ...current, [axis]: value } };
  snapshot({ transforms }, "transform", { target: selection, axis, value });
  safeCall("transform", selection, axis, value);
  safeCall("setVisibility", selection, !state.hidden[selection]);
}

function setWeather(weather) {
  if (!WEATHER_LABELS[weather]) return;
  const preset = WEATHER_PRESETS[weather] || {};
  snapshot({ weather, ...preset }, "weather", { weather, preset });
  safeCall("weather", weather);
  toast(`天象 · ${WEATHER_LABELS[weather]}`);
}

function setDayTime(value) {
  const dayTime = clamp(value, 0, 24);
  snapshot({ dayTime }, "daytime", { dayTime });
  safeCall("daytime", dayTime);
}

function resetAll() {
  const previous = state;
  state = { ...clone(DEFAULTS), hidden: {}, transforms: {} };
  syncUI();
  safeCall("resetAll", clone(state));
  emit("reset", { defaults: clone(DEFAULTS), previous: clone(previous) });
  toast("场景参数已复位");
}

function resetView() {
  safeCall("resetView");
  toast("视角已复位");
}

function setPressedState(key) {
  if (key === "grid") {
    snapshot({ grid: !state.grid }, "grid", { enabled: !state.grid });
    safeCall("grid", !state.grid);
  }
  if (key === "wireframe") {
    snapshot({ wireframe: !state.wireframe }, "wireframe", { enabled: !state.wireframe });
    safeCall("wireframe", !state.wireframe);
  }
}

function screenshot() {
  if (typeof sceneApi?.screenshot === "function") {
    const result = sceneApi.screenshot();
    if (result === false) toast("场景尚未准备就绪");
    return result;
  }
  toast("场景尚未准备就绪");
  return false;
}

function bindEvents() {
  document.querySelectorAll("[data-weather]").forEach((button) => {
    button.addEventListener("click", () => setWeather(button.dataset.weather));
  });

  const dayTime = byId("day-time");
  if (dayTime) dayTime.addEventListener("input", (event) => setDayTime(event.target.value));

  [
    ["tower-lights", "towerLights", "towerLights"],
    ["shadow-toggle", "shadows", "shadows"],
  ].forEach(([id, key, method]) => {
    const input = byId(id);
    if (!input) return;
    input.addEventListener("change", (event) => {
      const patch = { [key]: event.target.checked };
      snapshot(patch, key, patch);
      safeCall(method, event.target.checked);
    });
  });

  [
    ["wind-strength", "windStrength"],
    ["cloud-speed", "cloudSpeed"],
    ["waterfall-flow", "waterfallFlow"],
    ["bloom-strength", "bloomStrength"],
    ["fog-density", "fogDensity"],
  ].forEach(([id, key]) => {
    const input = byId(id);
    if (!input) return;
    input.addEventListener("input", (event) => {
      const value = Number(event.target.value);
      const patch = { [key]: value };
      snapshot(patch, key, patch);
      safeCall(key, value);
    });
  });

  document.querySelectorAll(".tree-row").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest(".visibility-button") || event.target.closest(".tree-caret")) return;
      select(row.dataset.target);
    });
    row.addEventListener("dblclick", (event) => {
      if (event.target.closest(".visibility-button")) return;
      select(row.dataset.target);
      safeCall("focus", row.dataset.target);
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select(row.dataset.target);
      }
    });
  });

  document.querySelectorAll(".visibility-button").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleVisibility(button.dataset.visibility);
    });
  });

  document.querySelectorAll(".tree-caret").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      button.setAttribute("aria-label", `${expanded ? "展开" : "收起"}${button.closest(".tree-row")?.querySelector(".tree-label")?.textContent?.trim() || "对象"}`);
      const parent = button.closest(".tree-row");
      let sibling = parent?.nextElementSibling;
      while (sibling) {
        if (sibling.classList.contains("tree-children")) {
          sibling.classList.toggle("is-collapsed", expanded);
          break;
        }
        sibling = sibling.nextElementSibling;
      }
    });
  });

  document.querySelectorAll("#rotate-x, #rotate-y, #rotate-z, #scale-uniform").forEach((input) => {
    input.addEventListener("input", () => {
      const axis = input.id === "rotate-x" ? "rx"
        : input.id === "rotate-y" ? "ry"
        : input.id === "rotate-z" ? "rz"
        : "scale";
      setTransform(axis, Number(input.value));
    });
  });

  const resetViewButton = byId("reset-view");
  if (resetViewButton) resetViewButton.addEventListener("click", resetView);
  const resetAllButton = byId("reset-all");
  if (resetAllButton) resetAllButton.addEventListener("click", resetAll);
  const gridButton = byId("grid-toggle");
  if (gridButton) gridButton.addEventListener("click", () => setPressedState("grid"));
  const wireframeButton = byId("wireframe-toggle");
  if (wireframeButton) wireframeButton.addEventListener("click", () => setPressedState("wireframe"));
  const screenshotButton = byId("screenshot");
  if (screenshotButton) screenshotButton.addEventListener("click", screenshot);

  const collapse = byId("environment-collapse");
  const panel = document.querySelector(".control-panel");
  if (collapse && panel) {
    collapse.addEventListener("click", () => {
      const collapsed = panel.classList.toggle("is-collapsed");
      collapse.setAttribute("aria-expanded", String(!collapsed));
      collapse.setAttribute("aria-label", collapsed ? "展开环境参数面板" : "收起环境参数面板");
    });
  }

  const canvas = byId("scene-canvas");
  if (canvas) {
    let pointerDown = false;
    canvas.addEventListener("pointerdown", () => {
      pointerDown = true;
      document.body.classList.add("is-dragging");
    });
    window.addEventListener("pointerup", () => {
      pointerDown = false;
      document.body.classList.remove("is-dragging");
    });
  }

  window.addEventListener("keydown", (event) => {
    const tag = document.activeElement?.tagName?.toLowerCase();
    if (tag === "input" || tag === "textarea" || event.metaKey || event.ctrlKey || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === "r") resetView();
    if (key === "w") setPressedState("wireframe");
  });
}

function setSceneAPI(api) {
  sceneApi = api || null;
  if (!sceneApi) return;
  // Re-apply the current UI state after the 3D world finishes loading.
  safeCall("daytime", state.dayTime);
  safeCall("weather", state.weather);
  safeCall("towerLights", state.towerLights);
  safeCall("windStrength", state.windStrength);
  safeCall("cloudSpeed", state.cloudSpeed);
  safeCall("waterfallFlow", state.waterfallFlow);
  safeCall("bloomStrength", state.bloomStrength);
  safeCall("fogDensity", state.fogDensity);
  safeCall("shadows", state.shadows);
  safeCall("grid", state.grid);
  safeCall("wireframe", state.wireframe);
  Object.entries(state.hidden).forEach(([target, hidden]) => safeCall("setVisibility", target, !hidden));
  Object.entries(state.transforms).forEach(([target, transform]) => {
    safeCall("transform", target, "rx", transform.rx ?? 0);
    safeCall("transform", target, "ry", transform.ry ?? 0);
    safeCall("transform", target, "rz", transform.rz ?? 0);
    safeCall("transform", target, "scale", transform.scale ?? 1);
    safeCall("setVisibility", target, !state.hidden[target]);
  });
  safeCall("select", state.selected, { silent: true });
}

const api = {
  get state() {
    return clone(state);
  },
  defaults: clone(DEFAULTS),
  subscribe(listener) {
    if (typeof listener !== "function") return () => {};
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  emit,
  select,
  toggleVisibility,
  setTransform,
  setWeather,
  setDayTime,
  resetAll,
  resetView,
  screenshot,
  toast,
  syncUI,
  setSceneAPI,
  setFps(fps) {
    const value = Math.round(Number(fps) || 0);
    const readout = byId("fps-readout");
    if (readout) readout.textContent = `${value} FPS`;
    const build = byId("build-fps");
    if (build) build.textContent = `${value} FPS`;
    document.body.classList.toggle("is-low-fps", value > 0 && value < 45);
  },
  setSelectionName(name) {
    const display = SELECTION_LABELS[name] || name;
    const selectionReadout = byId("selection-name");
    if (selectionReadout) selectionReadout.textContent = display;
    const calloutName = byId("callout-name");
    if (calloutName) calloutName.textContent = display;
  },
  flashCapture() {
    document.body.classList.add("is-capturing");
    window.setTimeout(() => document.body.classList.remove("is-capturing"), 320);
  },
};

window.sceneEditorUI = api;
document.dispatchEvent(new CustomEvent("scene-editor-ready"));

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindEvents, { once: true });
} else {
  bindEvents();
}

syncUI();

export default api;
export {
  DEFAULTS,
  WEATHER_LABELS,
  SELECTION_LABELS,
  api as sceneEditorUI,
};
