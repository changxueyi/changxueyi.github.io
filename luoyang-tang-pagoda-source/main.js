import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { buildWorld } from './editor-world.js';
import './scene-editor.js';

const TAU = Math.PI * 2;
const DEG = Math.PI / 180;
const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));
const smoothstep = (value) => {
  const t = clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
};
const $ = (id) => document.getElementById(id);
const weatherKey = (value) => ({ cloudsea: 'cloud-sea' }[value] || value);

const PRESETS = {
  clear: { hour: 15.5, fog: 0.014, bloom: 0.72, sun: 0xffe1ad, top: 0x4a9cb8, bottom: 0xf2c7a1, light: 1.0, cloud: 0.25, night: 0 },
  'cloud-sea': { hour: 11.2, fog: 0.024, bloom: 0.68, sun: 0xfff0d2, top: 0x5d8da5, bottom: 0xf1dfc7, light: 0.92, cloud: 0.82, night: 0 },
  mist: { hour: 7.15, fog: 0.036, bloom: 0.54, sun: 0xdfe9e2, top: 0x526d78, bottom: 0xbdc4bc, light: 0.64, cloud: 0.55, night: 0 },
  sunset: { hour: 16.2, fog: 0.0072, bloom: 0.66, sun: 0xffd3a0, top: 0x123b55, bottom: 0xe8b984, light: 1.08, cloud: 0.24, night: 0 },
  moon: { hour: 22.3, fog: 0.020, bloom: 1.08, sun: 0x9dbbe2, top: 0x07101f, bottom: 0x2e4654, light: 0.42, cloud: 0.15, night: 1 },
};

class LuoyangEditor {
  constructor() {
    this.canvas = $('scene-canvas');
    this.ui = window.sceneEditorUI;
    this.state = {};
    this.clock = new THREE.Clock();
    this.elapsed = 0;
    this.wallElapsed = 0;
    this.transformValues = new Map();
    this.selectedKey = 'pagoda';
    this.defaultSelectedKey = 'pagoda';
    this.selectedObject = null;
    this.pointerStart = new THREE.Vector2();
    this.raycaster = new THREE.Raycaster();
    this.pointerNdc = new THREE.Vector2();
    this.currentFps = 60;
    this.fpsFrames = 0;
    this.fpsElapsed = 0;
    this.materialList = [];
    this.materialWireframe = new Map();
    this.unsubscribe = null;
    this.lastTransformSignature = '';
    this.forceHighQuality = new URLSearchParams(window.location.search).get('quality') === 'high';
    this._animate = this.animate.bind(this);
    this._resize = this.resize.bind(this);
    this._onPointerDown = this.onPointerDown.bind(this);
    this._onPointerUp = this.onPointerUp.bind(this);
    this._onDoubleClick = this.onDoubleClick.bind(this);
    this._onKeyDown = this.onKeyDown.bind(this);
  }

  async init() {
    this.initRenderer();
    this.initScene();
    this.initCamera();
    this.initLights();
    this.initSky();
    this.initPostprocessing();
    this.initSelection();
    this.world = buildWorld(THREE, {
      onSelect: (key) => this.select(key),
      seed: 73129,
    });
    this.scene.add(this.world.root);
    const animatedRoots = new Set();
    const addAnimatedRoot = (value) => {
      const object = value?.object || value;
      if (object?.isObject3D) animatedRoots.add(object);
    };
    addAnimatedRoot(this.world.groups.dragon);
    addAnimatedRoot(this.world.groups.phoenix);
    addAnimatedRoot(this.world.groups.clouds);
    addAnimatedRoot(this.world.groups.waterfalls);
    addAnimatedRoot(this.world.groups.cranes);
    addAnimatedRoot(this.world.groups.satellites);
    this.world.root.traverse((object) => {
      if (object.isMesh && !object.isSkinnedMesh && !object.userData.noStaticMatrix && !object.userData.dynamic) {
        let cursor = object;
        let dynamic = false;
        while (cursor && cursor !== this.world.root) {
          if (animatedRoots.has(cursor)) { dynamic = true; break; }
          cursor = cursor.parent;
        }
        if (dynamic) return;
        object.updateMatrix();
        object.matrixAutoUpdate = false;
      }
    });
    this.collectMaterials();
    this.cacheBaseTransforms();
    this.bindSceneAPI();
    this.bindEvents();
    const uiState = this.ui?.state || {};
    this.applyState({ ...uiState, dayTime: uiState.weather === 'sunset' ? 16.2 : (uiState.dayTime ?? 16.2) }, true);
    const initHour = this.uiState?.dayTime ?? 16.2;
    this.syncReadouts(((initHour % 24) + 24) % 24, 0, 0, this.ui?.state || {});
    this.select(this.ui?.state?.selected || this.defaultSelectedKey, { silent: true });
    this.applyQueuedTransforms();
    this.resize();
    this.clock.start();
    this.animate();
    this.markReady();
  }

  initRenderer() {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas || undefined,
      antialias: false,
      alpha: false,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: true,
    });
    this.maxPixelRatio = 1.0;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.maxPixelRatio));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.info.autoReset = false;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    this.renderer.shadowMap.needsUpdate = true;
    if (this.canvas) {
      this.canvas.setAttribute('aria-label', '洛阳盛唐浮空古塔交互式体素场景');
      this.canvas.tabIndex = 0;
    }
  }

  initScene() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x7893a0);
    this.renderer.setClearColor(0x7893a0, 1);
    this.scene.fog = new THREE.FogExp2(0x9bb5b4, 0.0072);
    this.sunTarget = new THREE.Object3D();
    this.scene.add(this.sunTarget);
  }

  initCamera() {
    this.camera = new THREE.PerspectiveCamera(43, window.innerWidth / window.innerHeight, 0.1, 240);
    this.camera.position.set(28.5, 20.0, 33.0);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 5.3, 0);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.minDistance = 7;
    this.controls.maxDistance = 68;
    this.controls.minPolarAngle = 0.16;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.controls.rotateSpeed = 0.58;
    this.controls.zoomSpeed = 0.72;
    this.controls.panSpeed = 0.7;
    this.controls.autoRotateSpeed = 0.38;
    this.controls.update();
    this.defaultView = {
      position: this.camera.position.clone(),
      target: this.controls.target.clone(),
    };
  }

  initLights() {
    this.hemisphere = new THREE.HemisphereLight(0xb9e1e6, 0x51402f, 1.45);
    this.scene.add(this.hemisphere);

    this.sun = new THREE.DirectionalLight(0xffe1ad, 2.7);
    this.sun.position.set(-17, 26, 14);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(768, 768);
    this.sun.shadow.camera.left = -23;
    this.sun.shadow.camera.right = 23;
    this.sun.shadow.camera.top = 25;
    this.sun.shadow.camera.bottom = -20;
    this.sun.shadow.camera.near = 1;
    this.sun.shadow.camera.far = 72;
    this.sun.shadow.bias = -0.0005;
    this.sun.shadow.normalBias = 0.04;
    this.sun.target = this.sunTarget;
    this.scene.add(this.sun);

    this.fill = new THREE.DirectionalLight(0x6f9fb5, 0.55);
    this.fill.position.set(18, 13, -20);
    this.scene.add(this.fill);

    this.ambient = new THREE.AmbientLight(0xffffff, 0.18);
    this.scene.add(this.ambient);

    this.towerLight = new THREE.PointLight(0xffa84f, 0.3, 13, 1.8);
    this.towerLight.position.set(0, 6.2, 0);
    this.scene.add(this.towerLight);

    this.cameraFill = new THREE.DirectionalLight(0xfff0d2, 0.62);
    this.cameraFill.position.set(24, 18, 30);
    this.scene.add(this.cameraFill);

    this.rimLight = new THREE.DirectionalLight(0x9ed2c7, 0.28);
    this.rimLight.position.set(-22, 12, -26);
    this.scene.add(this.rimLight);

    this.nightFill = new THREE.DirectionalLight(0x6f8fbf, 0.0);
    this.nightFill.position.set(12, 28, 18);
    this.scene.add(this.nightFill);
  }

  initSky() {
    this.skyUniforms = {
      uTop: { value: new THREE.Color(0x495079) },
      uBottom: { value: new THREE.Color(0xf1a066) },
      uSunColor: { value: new THREE.Color(0xffa552) },
      uSunDirection: { value: new THREE.Vector3(-0.55, 0.25, 0.55).normalize() },
      uHaze: { value: 0.4 },
    };
    const material = new THREE.ShaderMaterial({
      uniforms: this.skyUniforms,
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
      toneMapped: false,
      vertexShader: `
        varying vec3 vDirection;
        void main() {
          vec4 world = modelMatrix * vec4(position, 1.0);
          vDirection = normalize(world.xyz - cameraPosition);
          gl_Position = projectionMatrix * viewMatrix * world;
        }
      `,
      fragmentShader: `
        varying vec3 vDirection;
        uniform vec3 uTop;
        uniform vec3 uBottom;
        uniform vec3 uSunColor;
        uniform vec3 uSunDirection;
        uniform float uHaze;
        void main() {
          float h = smoothstep(-0.02, 0.36, vDirection.y);
          vec3 col = mix(uBottom, uTop, h);
          float sun = max(dot(vDirection, uSunDirection), 0.0);
          col += uSunColor * pow(sun, 210.0) * 1.6;
          col += uSunColor * pow(sun, 12.0) * 0.12;
          col = mix(col, uBottom, uHaze * 0.10 * (1.0 - h));
          gl_FragColor = vec4(col, 1.0);
          #include <colorspace_fragment>
        }
      `,
    });
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(115, 32, 18), material);
    this.sky.frustumCulled = false;
    this.sky.renderOrder = -1000;
    this.scene.add(this.sky);

    const sunSprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: this.makeSunTexture(),
      color: 0xffffff,
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
      fog: false,
    }));
    sunSprite.scale.set(22, 22, 1);
    sunSprite.renderOrder = -900;
    this.sky.add(sunSprite);
    this.sunSprite = sunSprite;

  }


  makeSunTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 128;
    const ctx = canvas.getContext('2d');
    const grad = ctx.createRadialGradient(64, 64, 4, 64, 64, 60);
    grad.addColorStop(0, 'rgba(255,248,220,1)');
    grad.addColorStop(0.18, 'rgba(255,218,140,.85)');
    grad.addColorStop(0.48, 'rgba(255,165,80,.20)');
    grad.addColorStop(1, 'rgba(255,140,60,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 128, 128);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  initPostprocessing() {
    this.composer = new EffectComposer(this.renderer);
    this.composer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.qualityAdjusted ? 0.5 : 0.85));
    this.composer.setSize(window.innerWidth, window.innerHeight);
    this.renderPass = new RenderPass(this.scene, this.camera);
    this.composer.addPass(this.renderPass);
    this.bloomPass = new UnrealBloomPass(
      new THREE.Vector2(Math.round(window.innerWidth * 0.7), Math.round(window.innerHeight * 0.7)),
      0.82,
      0.44,
      0.8,
    );
    this.composer.addPass(this.bloomPass);
    this.composer.addPass(new OutputPass());
  }

  initSelection() {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(72), 3));
    this.selectionBox = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({
        color: 0xffd178,
        fog: false,
        transparent: true,
        opacity: 0.92,
        depthTest: false,
        depthWrite: false,
        toneMapped: false,
      }),
    );
    this.selectionBox.frustumCulled = false;
    this.selectionBox.renderOrder = 999;
    this.selectionBox.visible = false;
    this.scene.add(this.selectionBox);
  }

  collectMaterials() {
    const materials = new Set(this.world.materials ? Object.values(this.world.materials) : []);
    this.world.root.traverse((object) => {
      if (!object.material) return;
      const objectMaterials = Array.isArray(object.material) ? object.material : [object.material];
      objectMaterials.forEach((material) => material && materials.add(material));
    });
    this.materialList = [...materials].filter(Boolean);
    this.materialWireframe = new Map(this.materialList.map((material) => [material, Boolean(material.wireframe)]));
    if (this.pendingWireframe != null) this.applyWireframe(this.pendingWireframe);
  }

  cacheBaseTransforms() {
    const groups = this.world.groups || {};
    this.groupByObject = new Map();
    Object.entries(groups).forEach(([key, value]) => {
      const object = value?.object || value;
      if (object) this.groupByObject.set(object, key);
    });
    this.baseTransforms = new Map();
    Object.entries(groups).forEach(([key, value]) => {
      const object = value?.object || value;
      if (!object?.position) return;
      this.baseTransforms.set(key, {
        position: object.position.clone(),
        rotation: object.rotation.clone(),
        scale: object.scale.clone(),
        visible: object.visible,
      });
    });
  }

  bindSceneAPI() {
    if (!this.ui) return;
    this.ui.setSceneAPI({
      daytime: (hour) => this.updateState({ dayTime: Number(hour) }, 'daytime'),
      weather: (name) => {
        const key = weatherKey(name);
        const preset = PRESETS[key];
        this.updateState({ weather: key, ...(preset ? { fogDensity: preset.fog, bloomStrength: preset.bloom } : {}) }, 'weather');
        const fogInput = $('fog-density');
        if (fogInput && preset) fogInput.value = String(preset.fog);
        const bloomInput = $('bloom-strength');
        if (bloomInput && preset) bloomInput.value = String(preset.bloom);
        this.ui?.syncUI?.();
        const fogOutput = $('fog-density-value');
        if (fogOutput && preset) fogOutput.textContent = preset.fog.toFixed(3);
        const bloomOutput = $('bloom-strength-value');
        if (bloomOutput && preset) bloomOutput.textContent = preset.bloom.toFixed(2);
      },
      towerLights: (on) => this.updateState({ towerLights: Boolean(on) }, 'towerLights'),
      windStrength: (value) => this.updateState({ windStrength: Number(value) }, 'windStrength'),
      cloudSpeed: (value) => this.updateState({ cloudSpeed: Number(value) }, 'cloudSpeed'),
      waterfallFlow: (value) => this.updateState({ waterfallFlow: Number(value) }, 'waterfallFlow'),
      bloomStrength: (value) => this.updateState({ bloomStrength: Number(value) }, 'bloomStrength'),
      fogDensity: (value) => this.updateState({ fogDensity: Number(value) }, 'fogDensity'),
      shadows: (on) => this.updateState({ shadows: Boolean(on) }, 'shadows'),
      grid: (on) => this.updateState({ grid: Boolean(on) }, 'grid'),
      wireframe: (on) => this.updateState({ wireframe: Boolean(on) }, 'wireframe'),
      setVisibility: (target, visible) => this.setVisibility(target, visible),
      transform: (target, axis, value) => this.setTransform(target, axis, value),
      select: (target, options = {}) => this.select(target, options),
      focus: (target) => this.focus(target),
      resetView: () => this.resetView(),
      resetAll: (state) => this.resetAll(state),
      screenshot: () => this.screenshot(),
      getStats: () => window.LUOYANG_EDITOR_STATS?.() || null,
    });
    this.unsubscribe = this.ui.subscribe((payload) => {
      if (!payload || payload.silent) return;
      if (payload.type === 'reset') this.resetAll(payload.state || this.ui.state);
      if (payload.type === 'selection') this.syncSelectionUI(payload.selected);
    });
  }

  bindEvents() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener('pointerdown', this._onPointerDown);
    canvas.addEventListener('pointerup', this._onPointerUp);
    canvas.addEventListener('dblclick', this._onDoubleClick);
    window.addEventListener('resize', this._resize);
    window.addEventListener('keydown', this._onKeyDown, true);
    window.addEventListener('luoyang-command', (event) => this.runCommand(event.detail));
    document.addEventListener('visibilitychange', () => this.clock.getDelta());
    window.addEventListener('beforeunload', () => this.dispose(), { once: true });
    this.renderer.domElement.addEventListener('webglcontextlost', (event) => {
      event.preventDefault();
      this.ui?.toast?.('图形上下文暂时丢失');
    });
    this.renderer.domElement.addEventListener('webglcontextrestored', () => {
      this.ui?.toast?.('场景已恢复');
      this.resize();
    });
  }

  markReady() {
    window.sceneEditor = this;
    window.__luoyangEditor = this;
    window.LUOYANG_EDITOR_READY = true;
    window.LUOYANG_EDITOR_STATS = () => ({
      fps: Math.round(this.currentFps),
      drawCalls: this.lastRenderStats?.calls ?? 0,
      triangles: this.lastRenderStats?.triangles ?? 0,
      geometries: this.renderer?.info?.memory?.geometries ?? 0,
      textures: this.renderer?.info?.memory?.textures ?? 0,
      objects: (() => { let count = 0; this.world?.root?.traverse(() => { count += 1; }); return count; })(),
      frameMs: this.lastFrameMs || 0,
      quality: this.qualityAdjusted ? 'adaptive' : 'high',
      transforms: Object.fromEntries(this.transformValues),
      selected: this.selectedKey,
    });
    document.body.classList.add('is-ready');
    const status = $('status-text');
    if (status) status.textContent = '场景已就绪';
    const gl = this.renderer.getContext();
    const debug = gl.getExtension('WEBGL_debug_renderer_info');
    const gpu = debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : 'WebGL';
    this.renderer.domElement.dataset.renderer = gpu;
    document.dispatchEvent(new CustomEvent('luoyang-ready', { detail: { editor: this } }));
    this.ui?.setFps?.(this.currentFps || 60);
  }

  updateState(patch, changed = 'state') {
    this.applyState({ ...(this.ui?.state || this.uiState || this.state), ...patch }, false, changed);
  }

  applyState(state, initial = false, changed = '') {
    if (!state || !this.world) return;
    const s = {
      dayTime: Number(state.dayTime ?? 16.2),
      weather: state.weather || 'sunset',
      towerLights: state.towerLights !== false,
      windStrength: Number(state.windStrength ?? 0.56),
      cloudSpeed: Number(state.cloudSpeed ?? 0.42),
      waterfallFlow: Number(state.waterfallFlow ?? 1.3),
      bloomStrength: Number(state.bloomStrength ?? 0.82),
      fogDensity: Number(state.fogDensity ?? 0.0072),
      shadows: state.shadows !== false,
      grid: this.ui?.state?.grid ?? Boolean(state.grid),
      wireframe: this.ui?.state?.wireframe ?? Boolean(state.wireframe),
    };
    this.uiState = s;
    this.lastNight = null;
    if (changed === 'wireframe') { this.pendingWireframe = s.wireframe; this.applyWireframe(s.wireframe); }
    const p = PRESETS[weatherKey(s.weather)] || PRESETS.sunset;
    const hour = ((s.dayTime % 24) + 24) % 24;
    const sunAngle = ((hour - 6) / 24) * TAU;
    const sunHeight = Math.sin(sunAngle);
    const day = smoothstep((sunHeight + 0.35) / 0.55);
    const night = 1 - smoothstep((sunHeight + 0.22) / 0.30);
    const golden = clamp(1 - Math.abs(hour - 17.8) / 2.4, 0, 1) * smoothstep((sunHeight + 0.24) / 0.22);
    const presetNight = p.night || 0;
    let nightAmount = clamp(Math.max(night, presetNight * (1 - day * 0.35)), 0, 1);
    if (s.weather === 'clear' || s.weather === 'cloud-sea' || s.weather === 'mist') {
      nightAmount = night;
    }

    this.sun.position.set(Math.abs(Math.cos(sunAngle + 0.7)) * 31 + 8, 16 + Math.max(-8, sunHeight * 24), Math.abs(Math.sin(sunAngle + 0.7)) * 21 + 6);
    this.sun.intensity = (0.58 + day * 2.10) * (p.light ?? 1);
    this.sun.color.setHex(p.sun);
    if (nightAmount > 0.55) this.sun.color.setHex(0xa9c8ff);
    else if (nightAmount < 0.08) this.sun.color.setHex(p.sun);
    this.sun.color.lerp(new THREE.Color(0xffe7c4), clamp(day, 0, 1) * 0.22);
    const sunsetGlow = Math.exp(-Math.pow((hour - 18.5) / 1.18, 2));
    if (sunsetGlow > 0.02) this.sun.color.lerp(new THREE.Color(0xff6f36), sunsetGlow * 0.92);
    if (nightAmount > 0.25) this.sun.color.lerp(new THREE.Color(0x86addb), nightAmount * 0.82);
    this.sun.castShadow = s.shadows;
    this.renderer.shadowMap.enabled = s.shadows;
    if (s.shadows) this.renderer.shadowMap.needsUpdate = true;
    this.hemisphere.intensity = 0.62 + day * 0.96 + nightAmount * 0.10;
    this.hemisphere.color.setHex(nightAmount > 0.45 ? 0x7c9fc5 : 0xb9e1e6);
    this.hemisphere.groundColor.setHex(nightAmount > 0.45 ? 0x1a2633 : 0x49392b);
    this.fill.intensity = 0.34 + day * 0.36;
    this.cameraFill.intensity = 0.38 + day * 0.38;
    this.rimLight.intensity = 0.20 + day * 0.20;
    this.nightFill.intensity = 0.18 + nightAmount * 0.95;
    this.fill.color.setHex(nightAmount > 0.45 ? 0x547ab0 : 0x8db9c9);
    this.ambient.intensity = 0.30 + (1 - day) * 0.16 + nightAmount * 0.18;

    const fogBase = new THREE.Color(p.bottom);
    if (nightAmount > 0.05) fogBase.lerp(new THREE.Color(0x0b1220), nightAmount * 0.90);
    else fogBase.lerp(new THREE.Color(0xf3d6ac), clamp(day, 0, 1) * 0.10);
    fogBase.lerp(new THREE.Color(0xc97d62), golden * 0.18);
    this.scene.fog.color.copy(fogBase);
    this.scene.fog.density = Math.max(0.0012, s.fogDensity * 0.74);
    this.scene.background.copy(fogBase);
    this.skyUniforms.uTop.value.setHex(p.top).lerp(new THREE.Color(0x050a12), nightAmount * 0.86);
    this.skyUniforms.uBottom.value.copy(fogBase).lerp(new THREE.Color(0xffc06f), golden * 0.55);
    this.skyUniforms.uSunColor.value.copy(this.sun.color);
    this.skyUniforms.uSunDirection.value.copy(this.sun.position).normalize();
    if (this.sunSprite) this.sunSprite.position.copy(this.skyUniforms.uSunDirection.value).multiplyScalar(92);
    this.skyUniforms.uHaze.value = clamp(s.fogDensity * 12 + (p.cloud || 0) * 0.22, 0, 1);

    const lightsOn = s.towerLights ? 1 : 0;
    this.towerLight.intensity = lightsOn * (0.48 + nightAmount * 4.4);
    this.towerLight.distance = 12 + nightAmount * 7;
    if (this.world.animated?.setNight) this.world.animated.setNight(nightAmount * lightsOn);
    if (this.world.animated?.setWeather) this.world.animated.setWeather(weatherKey(s.weather), {
      wind: s.windStrength,
      cloudSpeed: s.cloudSpeed,
      waterfall: s.waterfallFlow,
      night: nightAmount,
      day,
      golden,
    });

    if (this.bloomPass) {
      this.bloomPass.strength = Math.max(0, Number(s.bloomStrength) || 0);
      this.bloomPass.radius = 0.44 + Math.min(2, Number(s.bloomStrength) || 0) * 0.08;
      this.bloomPass.threshold = 0.8 - nightAmount * 0.14;
      this.lastBloom = this.bloomPass.strength;
    }
    this.renderer.toneMappingExposure = 1.2 + day * 0.18 + nightAmount * 0.38 + golden * 0.18;
    this.lastNight = nightAmount;
    this.lastGolden = golden;
    this.applyWireframe(s.wireframe);
    this.toggleGrid(s.grid);
    this.world.animated?.setWaterfallFlow?.(s.waterfallFlow);
    this.world.animated?.update?.(this.elapsed, 0, {
      wind: s.windStrength,
      cloudSpeed: s.cloudSpeed,
      waterfall: s.waterfallFlow,
      night: nightAmount,
    });

    if (!initial) this.syncReadouts(hour, nightAmount, golden, this.ui?.state || s);
    if (this.selectedObject) this.updateSelectionBox();
  }

  syncReadouts(hour, night, golden, s = this.uiState || {}) {
    const stateHour = Number(s.dayTime ?? this.uiState?.dayTime ?? hour);
    s = s || this.ui?.state || this.uiState || {};
    const h = Math.floor(stateHour);
    const m = Math.round((stateHour - h) * 60);
    const time = `${String(h % 24).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    const timeReadout = $('scene-time-readout');
    if (timeReadout) timeReadout.textContent = time;
    const weatherValue = $('weather-value');
    const weatherLabels = { clear: '晴空', 'cloud-sea': '云海', mist: '烟雨迷雾', sunset: '盛唐落日', moon: '月夜灯火' };
    if (weatherValue) weatherValue.textContent = weatherLabels[s.weather] || weatherLabels[this.uiState?.weather] || s.weather;
    const tower = $('tower-lights');
    if (tower) tower.checked = s.towerLights;
    const shadows = $('shadow-toggle');
    if (shadows) shadows.checked = s.shadows;
    const dayOutput = $('day-time-value');
    if (dayOutput) dayOutput.textContent = time;
    const dayInput = $('day-time');
    if (dayInput && Number(dayInput.value) !== Number(s.dayTime)) dayInput.value = String(s.dayTime);
    const fogOutput = $('fog-density-value');
    if (fogOutput) fogOutput.textContent = Number(s.fogDensity).toFixed(3);
    const bloomOutput = $('bloom-strength-value');
    if (bloomOutput) bloomOutput.textContent = Number(s.bloomStrength).toFixed(2);
    const phase = $('phase-label');
    if (phase) phase.textContent = night > 0.55 ? '月夜 · 千灯初上' : hour < 8 ? '晨雾 · 洛水初醒' : golden > 0.28 ? '盛唐落日 · 金光塔刹' : '晴昼 · 天上宫阙';
  }

  applyWireframe(enabled) {
    if (!this.materialList.length) { this.pendingWireframe = Boolean(enabled); return; }
    const on = Boolean(enabled);
    this.materialList.forEach((material) => {
      if (on) material.wireframe = true;
      else material.wireframe = this.materialWireframe.get(material) || false;
      material.needsUpdate = true;
    });
  }

  toggleGrid(enabled) {
    if (!this.grid) {
      this.grid = new THREE.GridHelper(52, 52, 0xe7cfa2, 0x4f6f77);
      this.grid.name = '编辑器参考网格';
      this.grid.position.y = 0.015;
      const mats = Array.isArray(this.grid.material) ? this.grid.material : [this.grid.material];
      mats.forEach((mat) => {
        mat.transparent = true;
        mat.opacity = 0.22;
        mat.depthWrite = false;
      });
      this.grid.visible = Boolean(enabled);
      this.scene.add(this.grid);
    } else {
      this.grid.visible = Boolean(enabled);
    }
  }

  setVisibility(target, visible) {
    const object = this.resolveObject(target);
    if (!object) return;
    object.visible = Boolean(visible);
    if (target === 'cloudsWaterfalls') {
      const clouds = this.resolveObject('clouds');
      if (clouds && clouds !== object) clouds.visible = Boolean(visible);
    }
    if (object === this.selectedObject || this.isDescendant(object, this.selectedObject)) {
      this.selectionBox.visible = this.selectedObject?.visible && Boolean(visible);
    }
  }

  isDescendant(parent, child) {
    let cursor = child;
    while (cursor) {
      if (cursor === parent) return true;
      cursor = cursor.parent;
    }
    return false;
  }

  resolveObject(target) {
    const entry = this.world?.groups?.[target];
    if (entry) return entry.object || entry;
    if (target === 'cloudsWaterfalls') return this.world?.groups?.waterfalls || this.world?.groups?.clouds || null;
    return null;
  }

  setTransform(target, axis, value) {
    const object = this.resolveObject(target);
    if (!object) return;
    const key = String(target || this.selectedKey);
    const values = this.transformValues.get(key) || { rx: 0, ry: 0, rz: 0, scale: 1 };
    values[axis] = Number(value);
    this.transformValues.set(key, values);
    const base = this.baseTransforms?.get(key);
    const baseRot = base?.rotation || { x: 0, y: 0, z: 0 };
    object.rotation.set(
      (values.rx || 0) * DEG + (baseRot.x || 0),
      (values.ry || 0) * DEG + (baseRot.y || 0),
      (values.rz || 0) * DEG + (baseRot.z || 0),
    );
    const scale = clamp(values.scale ?? 1, 0.05, 4);
    object.scale.set(scale, scale, scale);
    this.selectionDirty = true;
    if (object === this.selectedObject) this.updateSelectionBox();
    this.lastTransformSignature = this.makeTransformSignature();
    this.applyTransformFeedback(key);
  }

  applyQueuedTransforms() {
    const transforms = this.ui?.state?.transforms || {};
    this.baseTransforms = this.baseTransforms || new Map();
    Object.entries(transforms).forEach(([target, values]) => {
      ['rx', 'ry', 'rz', 'scale'].forEach((axis) => {
        this.setTransform(target, axis, values[axis] ?? (axis === 'scale' ? 1 : 0));
      });
    });
  }

  applyTransformFeedback(target) {
    if (target !== this.selectedKey) return;
    const values = this.transformValues.get(target) || {};
    const set = (id, value) => { const input = $(id); if (input) input.value = String(value); };
    set('rotate-x', Math.round(values.rx || 0));
    set('rotate-y', Math.round(values.ry || 0));
    set('rotate-z', Math.round(values.rz || 0));
    set('scale-uniform', Number(values.scale ?? 1));
  }

  makeTransformSignature() {
    const selected = this.ui?.state?.selected || this.selectedKey;
    const t = this.transformValues.get(selected) || {};
    return [selected, t.rx || 0, t.ry || 0, t.rz || 0, t.scale ?? 1].join('|');
  }

  select(target, options = {}) {
    if (!target) return;
    const object = this.resolveObject(target);
    if (!object) return;
    this.selectedKey = target;
    this.selectedObject = object;
    this.syncSelectionUI(target, options.silent);
    this.applyTransformFeedback(target);
    this.selectionDirty = true;
    this.updateSelectionBox();
    if (!options.silent) this.ui?.setSelectionName?.(target);
  }

  syncSelectionUI(target, silent = false) {
    const label = target;
    const selectionName = $('selection-name');
    const calloutName = $('callout-name');
    if (selectionName) selectionName.textContent = this.ui ? (this.ui.state.selected === target ? selectionName.textContent : selectionName.textContent) : label;
    if (calloutName) calloutName.textContent = calloutName.textContent || label;
    if (silent) return;
    this.ui?.setSelectionName?.(target);
    this.ui?.syncUI?.();
  }

  updateSelectionBox() {
    const object = this.selectedObject;
    if (!object) {
      this.selectionBox.visible = false;
      return;
    }
    object.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(object);
    if (box.isEmpty()) {
      this.selectionBox.visible = false;
      return;
    }
    const visible = object.visible;
    this.selectionBox.visible = visible;
    if (!visible) return;
    box.expandByScalar(0.075);
    const { min, max } = box;
    const corners = [
      [min.x, min.y, min.z], [max.x, min.y, min.z], [max.x, min.y, max.z], [min.x, min.y, max.z],
      [min.x, max.y, min.z], [max.x, max.y, min.z], [max.x, max.y, max.z], [min.x, max.y, max.z],
    ];
    const edges = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
    const attr = this.selectionBox.geometry.attributes.position;
    let p = 0;
    edges.forEach(([a, b]) => {
      attr.array[p++] = corners[a][0];
      attr.array[p++] = corners[a][1];
      attr.array[p++] = corners[a][2];
      attr.array[p++] = corners[b][0];
      attr.array[p++] = corners[b][1];
      attr.array[p++] = corners[b][2];
    });
    attr.needsUpdate = true;
    this.selectionBox.geometry.computeBoundingSphere();
  }

  focus(target = this.selectedKey) {
    const object = this.resolveObject(target) || (target === 'cloudsWaterfalls' ? (this.resolveObject('clouds') || this.resolveObject('waterfalls')) : null);
    if (!object) return;
    const box = new THREE.Box3().setFromObject(object);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    const direction = this.camera.position.clone().sub(this.controls.target).normalize();
    const distance = clamp(size * 1.05, 8.5, 54);
    this.controls.target.copy(center);
    this.camera.position.copy(center).addScaledVector(direction, distance);
    this.controls.update();
    this.selectionDirty = true;
    this.updateSelectionBox();
  }

  resetView() {
    this.camera.position.copy(this.defaultView.position);
    this.controls.target.copy(this.defaultView.target);
    this.controls.update();
  }

  resetAll(state) {
    const next = state || this.ui?.state || {};
    this.transformValues.clear();
    ['rotate-x','rotate-y','rotate-z','scale-uniform'].forEach((id) => {
      const input = $(id);
      if (input) input.value = id === 'scale-uniform' ? '1' : '0';
      const output = $(`${id}-value`);
      if (output) output.textContent = id === 'scale-uniform' ? '1.00×' : '0°';
    });
    if (this.baseTransforms) {
      this.baseTransforms.forEach((base, key) => {
        const object = this.resolveObject(key);
        if (!object) return;
        object.position.copy(base.position);
        object.rotation.copy(base.rotation);
        object.scale.copy(base.scale);
        object.visible = base.visible;
      });
    }
    this.applyState({
      dayTime: next.dayTime ?? 16.2,
      weather: next.weather || 'sunset',
      towerLights: next.towerLights !== false,
      windStrength: next.windStrength ?? 0.56,
      cloudSpeed: next.cloudSpeed ?? 0.42,
      waterfallFlow: next.waterfallFlow ?? 1.3,
      bloomStrength: next.bloomStrength ?? 0.82,
      fogDensity: next.fogDensity ?? 0.0072,
      shadows: next.shadows !== false,
      grid: this.ui?.state?.grid ?? Boolean(next.grid),
      wireframe: this.ui?.state?.wireframe ?? Boolean(next.wireframe),
    }, true, 'all');
    this.selectedKey = next.selected || this.defaultSelectedKey;
    const selectedRow = document.querySelector(`[data-target="${this.selectedKey}"]`);
    if (selectedRow) {
      selectedRow.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    } else {
      this.select(this.selectedKey, { silent: true });
    }
    this.applyQueuedTransforms();
    this.applyTransformFeedback(this.selectedKey);
    this.resetView();
    this.ui?.syncUI?.();
    ['day-time','wind-strength','cloud-speed','waterfall-flow','bloom-strength','fog-density'].forEach((id) => {
      const input = $(id);
      if (!input) return;
      const key = id.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      const fallback = this.ui?.defaults?.[key];
      if (fallback != null) input.value = String(fallback);
    });
    this.ui?.syncUI?.();
    this.syncReadouts(((this.uiState?.dayTime ?? 16.2) % 24), this.lastNight ?? 0, this.lastGolden ?? 0, this.ui?.state || this.uiState);
  }

  screenshot() {
    if (!this.renderer || !this.scene || !this.camera) return false;
    let selectionVisible = this.selectionBox.visible;
    let gridVisible = this.grid?.visible;
    try {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const previousRatio = this.renderer.getPixelRatio();
      const previousComposerRatio = this.composer.getPixelRatio?.() ?? previousRatio;
      const captureRatio = Math.min(2, Math.max(1.35, 2400 / Math.max(width, height)));
      this.renderer.setPixelRatio(captureRatio);
      this.composer.setPixelRatio(captureRatio);
      this.renderer.setSize(width, height, false);
      this.composer.setSize(width, height);
      this.selectionBox.visible = false;
      if (this.grid) this.grid.visible = false;
      this.composer.render();
      this.renderer.getContext().finish();
      const url = this.renderer.domElement.toDataURL('image/png');
      this.selectionBox.visible = selectionVisible;
      if (this.grid) this.grid.visible = Boolean(gridVisible);
      this.renderer.setPixelRatio(previousRatio);
      this.composer.setPixelRatio(previousComposerRatio);
      this.renderer.setSize(width, height, false);
      this.composer.setSize(width, height);
      const link = document.createElement('a');
      const date = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const stamp = `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
      link.download = `luoyang-tang-pagoda-${stamp}.png`;
      link.href = url;
      document.body.appendChild(link);
      link.click();
      link.remove();
      this.ui?.flashCapture?.();
      this.ui?.toast?.('高清截图已导出');
      return true;
    } catch (error) {
      this.selectionBox.visible = selectionVisible;
      if (this.grid) this.grid.visible = Boolean(gridVisible);
      this.renderer.setPixelRatio(this.maxPixelRatio || 1);
      this.composer.setPixelRatio(this.lowQualityApplied ? 0.42 : (this.qualityAdjusted ? 0.5 : 0.85));
      this.renderer.setSize(window.innerWidth, window.innerHeight, false);
      this.composer.setSize(window.innerWidth, window.innerHeight);
      this.selectionDirty = true;
      console.error('[LuoyangEditor] screenshot failed', error);
      this.ui?.toast?.('截图导出失败');
      return false;
    }
  }

  runCommand(detail) {
    if (!detail) return;
    if (detail.action === 'reset-view') this.resetView();
    if (detail.action === 'reset-all') this.resetAll(detail.state);
    if (detail.action === 'grid') {
      const button = $('grid-toggle');
      const desired = detail.value == null ? !this.ui?.state?.grid : Boolean(detail.value);
      if (button && Boolean(this.ui?.state?.grid) !== desired) button.click();
      else this.updateState({ grid: desired }, 'grid');
    }
    if (detail.action === 'wireframe') {
      const button = $('wireframe-toggle');
      const desired = detail.value == null ? !this.ui?.state?.wireframe : Boolean(detail.value);
      if (button && Boolean(this.ui?.state?.wireframe) !== desired) button.click();
      else this.updateState({ wireframe: desired }, 'wireframe');
    }
    if (detail.action === 'screenshot') this.screenshot();
    if (detail.action === 'focus') this.focus(detail.target);
  }

  onPointerDown(event) {
    this.pointerStart.set(event.clientX, event.clientY);
  }

  onPointerUp(event) {
    if (event.button !== 0) return;
    if (this.pointerStart.distanceTo(new THREE.Vector2(event.clientX, event.clientY)) > 5) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointerNdc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointerNdc.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointerNdc, this.camera);
    const hits = this.raycaster.intersectObject(this.world.root, true);
    for (const hit of hits) {
      let node = hit.object;
      let hidden = false;
      while (node) {
        if (!node.visible) hidden = true;
        if (node.userData?.editorKey) break;
        node = node.parent;
      }
      if (hidden) continue;
      const key = node?.userData?.editorKey || this.findEditorKey(hit.object);
      if (key) {
        this.select(key);
        this.ui?.select?.(key, { silent: true });
        return;
      }
    }
  }

  findEditorKey(object) {
    let node = object;
    while (node) {
      const key = this.groupByObject?.get(node);
      if (key) {
        const map = { clouds: 'cloudsWaterfalls', waterfalls: 'cloudsWaterfalls', '浮空主岛': 'island', pagodaBase: 'pagodaBase', pagodaBody: 'pagodaBody', pagodaFinial: 'pagodaFinial', satellites: 'island', dragon: 'dragon', phoenix: 'phoenix', vegetation: 'vegetation', island: 'island', pagoda: 'pagoda' };
        return map[key] || key;
      }
      node = node.parent;
    }
    return null;
  }

  onDoubleClick(event) {
    if (event.target.closest?.('.glass-panel, .bottom-toolbar, .masthead')) return;
    this.resetView();
  }

  onKeyDown(event) {
    if (event.defaultPrevented) return;
    const tag = document.activeElement?.tagName?.toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea' || event.metaKey || event.ctrlKey || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === 'f') { event.preventDefault(); event.stopImmediatePropagation(); this.focus(this.selectedKey); }
    if (key === 'g') {
      event.preventDefault();
      event.stopImmediatePropagation();
      document.querySelector('#grid-toggle')?.click();
    }
    if (key === 'w') {
      event.preventDefault();
      event.stopImmediatePropagation();
      document.querySelector('#wireframe-toggle')?.click();
    }
    if (key === 'escape') {
      event.preventDefault();
      event.stopImmediatePropagation();
      this.selectedObject = null;
      this.selectionBox.visible = false;
    }
  }

  resize() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    this.camera.aspect = width / height;
    this.camera.fov = width / height < 0.85 ? 55 : 43;
    this.camera.updateProjectionMatrix();
    this.maxPixelRatio = this.lowQualityApplied ? 0.58 : (this.qualityAdjusted ? 0.68 : 1.0);
    this.renderer.setPixelRatio(this.maxPixelRatio);
    this.renderer.setSize(width, height, false);
    if (this.composer) {
      this.composer.setPixelRatio(this.lowQualityApplied ? 0.42 : (this.qualityAdjusted ? 0.5 : 0.85));
      this.composer.setSize(width, height);
    }
    this.bloomPass?.setSize(width, height);
    if (this.ui?.state?.bloomStrength != null) this.bloomPass.strength = Math.max(0, Number(this.ui.state.bloomStrength) || 0);
  }

  adaptQuality(fps) {
    if (this.forceHighQuality) return;
    if (!this.qualityAdjusted && this.wallElapsed > 5 && fps < 24) {
      this.qualityAdjusted = true;
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 0.68));
      this.composer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 0.5));
      this.sun.shadow.mapSize.set(512, 512);
      if (this.sun.shadow.map) {
        this.sun.shadow.map.dispose();
        this.sun.shadow.map = null;
      }
      this.renderer.shadowMap.needsUpdate = true;
      this.resize();
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 0.68));
      this.composer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 0.5));
      this.composer.setSize(window.innerWidth, window.innerHeight);
    }
    if (this.qualityAdjusted && !this.lowQualityApplied && this.wallElapsed > 8 && fps < 15) {
      this.lowQualityApplied = true;
      this.sun.shadow.mapSize.set(512, 512);
      this.sun.shadow.map?.dispose();
      this.sun.shadow.map = null;
      this.renderer.shadowMap.needsUpdate = true;
      this.bloomPass.enabled = true;
      this.renderer.setPixelRatio(0.58);
      this.composer.setPixelRatio(0.42);
      this.resize();
      this.renderer.setPixelRatio(0.58);
      this.composer.setPixelRatio(0.42);
      this.composer.setSize(window.innerWidth, window.innerHeight);
      this.ui?.toast?.('已启用轻量渲染');
    }
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.unsubscribe?.();
    this.controls?.dispose();
    this.composer?.dispose?.();
    this.renderer?.dispose();
  }

  animate() {
    if (this.disposed) return;
    requestAnimationFrame(this._animate);
    if (document.hidden) { this.clock.getDelta(); return; }
    const rawDelta = this.clock.getDelta();
    const rawDt = Number.isFinite(rawDelta) ? rawDelta : 0.016;
    const dt = Math.min(rawDt, 0.05);
    this.elapsed += Math.min(rawDt, 0.5);
    this.wallElapsed += rawDt;
    this.controls.update();
    const params = {
      wind: this.uiState?.windStrength ?? 0.56,
      cloudSpeed: this.uiState?.cloudSpeed ?? 0.42,
      waterfall: this.uiState?.waterfallFlow ?? 1.3,
    };
    this.world.animated?.update?.(this.elapsed, dt, params);
    if (this.selectedObject && (this.selectedKey === 'dragon' || this.selectedKey === 'phoenix') && this.fpsFrames % 3 === 0) this.selectionDirty = true;
    this.shadowTimer = (this.shadowTimer || 0) + rawDt;
    if (this.sun.castShadow && this.shadowTimer > 0.18) {
      this.renderer.shadowMap.needsUpdate = true;
      this.shadowTimer = 0;
    }
    if (this.selectionBox.visible && (this.selectionDirty || this.elapsed < 1)) {
      this.updateSelectionBox();
      this.selectionDirty = false;
    }
    this.sky.position.copy(this.camera.position);

    this.fpsFrames++;
    this.fpsElapsed += rawDt;
    this.lastFrameMs = rawDt * 1000;
    if (this.fpsElapsed >= 0.5) {
      const instantFps = this.fpsFrames / this.fpsElapsed;
      this.currentFps = this.currentFps ? this.currentFps * 0.7 + instantFps * 0.3 : instantFps;
      this.fpsFrames = 0;
      this.fpsElapsed = 0;
      this.ui?.setFps?.(this.currentFps);
      const fpsChip = $('fps-readout');
      if (fpsChip) fpsChip.title = this.lowQualityApplied ? '轻量渲染' : this.qualityAdjusted ? '自适应画质' : '高画质';
      this.adaptQuality(this.currentFps);
    }
    this.renderer.info.reset();
    this.composer.render();
    this.lastRenderStats = {
      calls: this.renderer.info.render.calls,
      triangles: this.renderer.info.render.triangles,
      points: this.renderer.info.render.points,
      lines: this.renderer.info.render.lines,
    };
  }
}

const editor = new LuoyangEditor();
editor.init().catch((error) => {
  console.error('[LuoyangEditor] initialization failed', error);
  window.LUOYANG_EDITOR_ERROR = String(error?.stack || error);
  const canvas = $('scene-canvas');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const w = canvas.width || 1280;
      const h = canvas.height || 720;
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, '#1d3038');
      grad.addColorStop(0.55, '#7b5c50');
      grad.addColorStop(1, '#0b1118');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = 'rgba(247,238,220,.92)';
      ctx.font = `${Math.max(16, Math.round(w / 55))}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText('洛阳盛唐 · 浮空古塔', w / 2, h / 2 - 12);
      ctx.fillStyle = 'rgba(247,238,220,.62)';
      ctx.font = `${Math.max(12, Math.round(w / 85))}px sans-serif`;
      ctx.fillText('当前浏览器无法初始化 WebGL2，请开启硬件加速或换用支持 WebGL 的浏览器。', w / 2, h / 2 + 20);
    }
  }
  const loading = $('loading');
  if (loading) {
    loading.classList.add('failed');
    const detail = loading.querySelector('[data-loading-detail]');
    if (detail) detail.textContent = String(error?.message || error);
  }
  window.sceneEditorUI?.toast?.('场景加载失败，请查看控制台');
});

export { LuoyangEditor };
