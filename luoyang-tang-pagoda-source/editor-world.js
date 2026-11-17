import * as THREE from 'three';

const TAU = Math.PI * 2;
const UP = new THREE.Vector3(0, 1, 0);
const scratch = new THREE.Object3D();
const tempColor = new THREE.Color();
let boxBatches = null;
let boxesEnabled = false;

function queueBox(parent, material, size, pos, rot) {
  if (!boxesEnabled || !boxBatches) return null;
  if (parent?.updateWorldMatrix) parent.updateWorldMatrix(true, false);
  let top = parent;
  while (top && !top.userData?.editorKey && top.parent) top = top.parent;
  if (!top) top = parent;
  const key = material.uuid + '|' + (top?.uuid || parent.uuid);
  let batch = boxBatches.get(key);
  if (!batch) {
    if (top?.updateWorldMatrix) top.updateWorldMatrix(true, false);
    const inverse = top.matrixWorld.clone().invert();
    batch = { parent: top, material, items: [], inverse };
    boxBatches.set(key, batch);
  }
  const local = batch.inverse.clone().multiply(parent.matrixWorld);
  batch.items.push({
    size: size.slice(), pos: pos.slice(), rot: rot ? rot.slice() : null,
    matrix: local, quaternion: parent.quaternion ? parent.quaternion.clone() : null,
  });
  return null;
}


function queueBoxMatrix(parent, material, size, matrix) {
  if (!boxesEnabled || !boxBatches) return null;
  if (parent?.updateWorldMatrix) parent.updateWorldMatrix(true, false);
  let top = parent;
  while (top && !top.userData?.editorKey && top.parent) top = top.parent;
  if (!top) top = parent;
  const key = material.uuid + '|' + (top?.uuid || parent.uuid);
  let batch = boxBatches.get(key);
  if (!batch) {
    if (top?.updateWorldMatrix) top.updateWorldMatrix(true, false);
    const inverse = top.matrixWorld.clone().invert();
    batch = { parent: top, material, items: [], inverse };
    boxBatches.set(key, batch);
  }
  const local = batch.inverse.clone().multiply(parent.matrixWorld).multiply(matrix);
  batch.items.push({ size: size.slice(), pos: [0,0,0], rot: null, matrix: local, directMatrix: true });
  return null;
}

function flushBoxes() {
  if (!boxBatches) return;
  const quat = new THREE.Quaternion();
  const euler = new THREE.Euler();
  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3();
  const scale = new THREE.Vector3();
  for (const batch of boxBatches.values()) {
    if (!batch.items.length) continue;
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const instanced = new THREE.InstancedMesh(geometry, batch.material, batch.items.length);
    instanced.name = 'voxel-batch';
    instanced.castShadow = batch.material.__noShadow !== true && batch.items.length > 100;
    instanced.receiveShadow = true;
    instanced.userData.isBoxBatch = true;
    batch.items.forEach((item, i) => {
      euler.set(item.rot?.[0] || 0, item.rot?.[1] || 0, item.rot?.[2] || 0);
      quat.setFromEuler(euler);
      position.set(item.pos[0], item.pos[1], item.pos[2]);
      scale.set(item.size[0], item.size[1], item.size[2]);
      if (item.directMatrix) {
        matrix.copy(item.matrix);
      } else {
        matrix.compose(position, quat, scale);
        matrix.premultiply(item.matrix || new T.Matrix4());
      }
      instanced.setMatrixAt(i, matrix);
    });
    instanced.instanceMatrix.needsUpdate = true;
    instanced.computeBoundingSphere();
    instanced.frustumCulled = true;
    batch.parent.add(instanced);
  }
  boxBatches.clear();
}

function rng(seed = 73129) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function hash3(x, y, z) {
  const n = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453123;
  return n - Math.floor(n);
}

function mat(color, extra = {}) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: 0.92,
    metalness: 0,
    flatShading: false,
    ...extra,
  });
}

function canvasTexture(kind, palette, size = 128) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const rand = rng(9127 + kind.length * 31 + palette.length);
  ctx.fillStyle = palette[0];
  ctx.fillRect(0, 0, size, size);
  const step = kind === 'stone' ? 8 : 4;
  for (let y = 0; y < size; y += step) {
    for (let x = 0; x < size; x += step) {
      const v = rand();
      ctx.globalAlpha = 0.08 + v * 0.23;
      ctx.fillStyle = palette[1 + Math.floor(rand() * (palette.length - 1))];
      ctx.fillRect(x, y, step - 1, step - 1);
    }
  }
  if (kind === 'wood') {
    ctx.globalAlpha = 0.22;
    ctx.strokeStyle = palette[palette.length - 1];
    for (let i = 0; i < 14; i++) {
      ctx.beginPath();
      const y = rand() * size;
      ctx.moveTo(0, y);
      for (let x = 0; x < size; x += 8) ctx.lineTo(x, y + Math.sin(x * 0.08 + i) * 2);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 2;
  return tex;
}

function glowTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext('2d');
  const g = ctx.createRadialGradient(64, 64, 2, 64, 64, 62);
  g.addColorStop(0, 'rgba(255,245,190,1)');
  g.addColorStop(0.2, 'rgba(255,204,96,.8)');
  g.addColorStop(1, 'rgba(255,170,80,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}

function addBox(parent, material, size, pos, rot = null) {
  if (boxesEnabled) return queueBox(parent, material, size, pos, rot);
  const geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(pos[0], pos[1], pos[2]);
  if (rot) mesh.rotation.set(rot[0], rot[1], rot[2]);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function addCyl(parent, material, rt, rb, h, seg, pos, rot = null) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), material);
  mesh.position.set(pos[0], pos[1], pos[2]);
  if (rot) mesh.rotation.set(rot[0], rot[1], rot[2]);
  mesh.castShadow = rt > 1.2 || rb > 1.2;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function addSphere(parent, material, r, detail, pos, scale = null) {
  const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(r, detail), material);
  mesh.position.set(pos[0], pos[1], pos[2]);
  if (scale) mesh.scale.set(scale[0], scale[1], scale[2]);
  mesh.castShadow = false;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function lineBetween(a, b, thickness, material, parent) {
  if (boxesEnabled) {
    const midW = a.clone().add(b).multiplyScalar(0.5);
    const len = a.distanceTo(b);
    const quat = new THREE.Quaternion().setFromUnitVectors(UP, b.clone().sub(a).normalize());
    const m = new THREE.Matrix4().compose(midW, quat, new THREE.Vector3(1,1,1));
    queueBoxMatrix(parent, material, [thickness, len, thickness], m);
    return null;
  }
  const mid = a.clone().add(b).multiplyScalar(0.5);
  const len = a.distanceTo(b);
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(thickness, len, thickness), material);
  mesh.position.copy(mid);
  mesh.quaternion.setFromUnitVectors(UP, b.clone().sub(a).normalize());
  mesh.castShadow = false;
  parent.add(mesh);
  return mesh;
}


function instancedBoxes(parent, material, list, name = 'voxels') {
  if (!list.length) return null;
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const tinted = list.some((item) => item.c !== undefined);
  const instanceMaterial = tinted && material.color
    ? material.clone()
    : material;
  if (instanceMaterial !== material) {
    instanceMaterial.color.set(0xffffff);
    instanceMaterial.vertexColors = false;
  }
  const mesh = new THREE.InstancedMesh(geometry, instanceMaterial, list.length);
  mesh.name = name;
  const o = new THREE.Object3D();
  const c = new THREE.Color();
  for (let i = 0; i < list.length; i++) {
    const item = list[i];
    o.position.set(item.p[0], item.p[1], item.p[2]);
    o.rotation.set(item.r ? item.r[0] : 0, item.r ? item.r[1] : 0, item.r ? item.r[2] : 0);
    o.scale.set(item.s[0], item.s[1], item.s[2]);
    o.updateMatrix();
    mesh.setMatrixAt(i, o.matrix);
    if (item.c !== undefined) {
      c.set(item.c);
      mesh.setColorAt(i, c);
    }
  }
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mesh.castShadow = list.length > 80;
  mesh.receiveShadow = true;
  mesh.frustumCulled = true;
  mesh.geometry.computeBoundingSphere();
  parent.add(mesh);
  return mesh;
}

function octagon(radius, y = 0) {
  const pts = [];
  for (let i = 0; i < 8; i++) {
    const a = i / 8 * TAU + Math.PI / 8;
    pts.push(new THREE.Vector2(Math.cos(a) * radius, Math.sin(a) * radius));
  }
  return pts;
}

function makeArchShape(width, height) {
  const s = new THREE.Shape();
  const w = width / 2;
  s.moveTo(-w, 0);
  s.lineTo(-w, height * 0.58);
  s.quadraticCurveTo(-w, height, 0, height);
  s.quadraticCurveTo(w, height, w, height * 0.58);
  s.lineTo(w, 0);
  s.lineTo(-w, 0);
  return s;
}

function ring(radius, count, offset = 0) {
  const out = [];
  for (let i = 0; i < count; i++) {
    const a = i / count * TAU + offset;
    out.push([Math.cos(a) * radius, Math.sin(a) * radius, a]);
  }
  return out;
}

export function buildWorld(THREE_NS = THREE, options = {}) {
  const T = THREE_NS;
  const random = rng(options.seed || 73129);
  const root = new T.Group();
  boxBatches = new Map();
  boxBatches.root = root;
  boxesEnabled = true;
  root.name = '洛阳盛唐浮空岛';
  const groups = {};
  const targets = {};
  const materials = {};
  const textures = {};
  const animated = { mixers: [], spinners: [], floaters: [], petals: null, waterfallMists: [], glowSprites: [], localMaterials: [] };

  const mkGroup = (name, parent = root, targetKey = name) => {
    const g = new T.Group();
    g.name = name;
    if (targetKey) g.userData.editorKey = targetKey;
    parent.add(g);
    groups[name] = g;
    if (targetKey) targets[targetKey] = g;
    return g;
  };

  const stoneTex = canvasTexture('stone', ['#8f887b', '#bcb5a5', '#756f65', '#d0c8b6']);
  stoneTex.repeat.set(3, 3);
  const whiteTex = canvasTexture('stone', ['#ded7c2', '#f1ead8', '#c1baa8', '#fff9e8']);
  whiteTex.repeat.set(2, 2);
  const woodTex = canvasTexture('wood', ['#772f24', '#a74b32', '#4c1b17', '#c56d43']);
  woodTex.repeat.set(4, 2);
  const roofTex = canvasTexture('stone', ['#34494b', '#4d6260', '#233336', '#6d7770']);
  roofTex.repeat.set(4, 2);
  const grassTex = canvasTexture('organic', ['#426746', '#6e8f4a', '#304f3a', '#a3a756']);
  grassTex.repeat.set(6, 6);
  textures.stone = stoneTex;
  textures.white = whiteTex;
  textures.wood = woodTex;
  textures.roof = roofTex;
  textures.grass = grassTex;

  materials.stone = mat(0xa8a18d, { map: stoneTex, roughness: 0.95 });
  materials.darkStone = mat(0x686f68, { map: stoneTex });
  materials.white = mat(0xe9e1cc, { map: whiteTex, roughness: 0.76 });
  materials.plaster = mat(0xe7ddc7, { map: whiteTex });
  materials.wood = mat(0x8c3428, { map: woodTex, roughness: 0.72 });
  materials.woodDark = mat(0x4b211c, { map: woodTex });
  materials.roof = mat(0x294348, { map: roofTex, roughness: 0.74 });
  materials.roofEdge = mat(0x60706a, { roughness: 0.64 });
  materials.gold = mat(0xd6aa43, { metalness: 0.72, roughness: 0.3 });
  materials.goldBright = mat(0xffd66d, { metalness: 0.56, roughness: 0.2, emissive: 0x6b3b00, emissiveIntensity: 0.25 });
  materials.grass = mat(0x3f6f38, { map: grassTex });
  materials.grassLight = mat(0x6d963f, { map: grassTex });
  materials.earth = mat(0x70523a, { map: stoneTex });
  materials.rock = mat(0x59615b, { map: stoneTex });
  materials.basalt = mat(0x303c40, { map: stoneTex });
  materials.water = new T.MeshPhysicalMaterial({ color: 0x63b9c2, transparent: true, opacity: 0.74, roughness: 0.18, metalness: 0.02, transmission: 0.08, side: T.DoubleSide });
  materials.foam = new T.MeshBasicMaterial({ color: 0xe9fbff, transparent: true, opacity: 0.78 });
  materials.lotus = mat(0xf5a7b9, { emissive: 0x4f1420, emissiveIntensity: 0.08 });
  materials.leaf = mat(0x2b6636);
  materials.pine = mat(0x1d5035);
  materials.pineLight = mat(0x49734e);
  materials.blossom = mat(0xef8aa1, { emissive: 0x3d1220, emissiveIntensity: 0.12 });
  materials.ginkgo = mat(0xd8ae48, { emissive: 0x493500, emissiveIntensity: 0.1 });
  materials.rockDark = mat(0x393e3e);
  materials.bronze = mat(0x49645c, { metalness: 0.45, roughness: 0.52 });
  materials.skin = mat(0xe9b98f);
  materials.dragon = mat(0x2d8f86, { metalness: 0.24, roughness: 0.55 });
  materials.dragonLight = mat(0x6bd0b5, { metalness: 0.3, roughness: 0.48, emissive: 0x073c34, emissiveIntensity: 0.22 });
  materials.dragonGold = mat(0xe8bd55, { metalness: 0.64, roughness: 0.32 });
  materials.phoenix = mat(0xc33d29, { metalness: 0.15, roughness: 0.6 });
  materials.phoenixOrange = mat(0xee7a30, { emissive: 0x6c1a05, emissiveIntensity: 0.35 });
  materials.phoenixGold = mat(0xf0c75e, { metalness: 0.45, roughness: 0.38 });
  materials.phoenixBlue = mat(0x426d91, { metalness: 0.18, roughness: 0.5 });
  materials.whiteBird = mat(0xf1e9d4, { emissive: 0x443b29, emissiveIntensity: 0.1 });
  materials.eye = mat(0x151d1b, { roughness: 0.25 });
  materials.petal = new T.MeshBasicMaterial({ color: 0xf4a8bc, side: T.DoubleSide });
  materials.glow = new T.SpriteMaterial({ map: glowTexture(), color: 0xffd98a, transparent: true, opacity: 0.6, depthWrite: false, blending: T.AdditiveBlending });
  materials.glow.userData.baseOpacity = 0.6;
  textures.glow = materials.glow.map;

  // Floating island: broad garden plateau, stratified cliff, stalactite underside.
  const island = mkGroup('island', root, 'island');
  const islandTop = mkGroup('浮空主岛', island, null);
  const base = addCyl(islandTop, materials.grass, 12.2, 12.65, 1.0, 12, [0, 0.1, 0]);
  base.scale.set(1.08, 1, 0.92);
  const soil = addCyl(islandTop, materials.earth, 12.6, 10.9, 1.65, 12, [0, -1.1, 0]);
  soil.scale.set(1.05, 1, 0.92);
  const rock1 = addCyl(islandTop, materials.rock, 10.9, 8.3, 3.2, 10, [0, -3.25, 0]);
  rock1.rotation.y = 0.17;
  const rock2 = addCyl(islandTop, materials.rockDark, 8.3, 5.1, 3.2, 9, [0, -6.4, 0]);
  rock2.rotation.y = 0.37;
  const rootBottom = addCyl(islandTop, materials.basalt, 5.2, 0.5, 5.4, 8, [0, -10.1, 0]);
  rootBottom.rotation.y = 0.2;

  const cliffBlocks = [];
  const vineBlocks = [];
  for (let i = 0; i < 92; i++) {
    const a = random() * TAU;
    const rr = 8.8 + random() * 4.1;
    const y = -2.3 - random() * 9.2;
    const taper = Math.max(0.15, 1 - (-y / 12) * 0.72);
    cliffBlocks.push({
      p: [Math.cos(a) * rr * taper, y, Math.sin(a) * rr * taper * 0.92],
      s: [0.35 + random() * 0.9, 0.3 + random() * 1.1, 0.35 + random() * 0.9],
      r: [random() * 0.3, a + random() * 0.4, random() * 0.28],
      c: [0x48534e, 0x687064, 0x353d3b, 0x7e806e][i % 4],
    });
  }
  instancedBoxes(islandTop, materials.rock, cliffBlocks, '岛体风化岩块');

  for (let i = 0; i < 58; i++) {
    const a = random() * TAU;
    const rr = 7.5 + random() * 4.7;
    const length = 1.4 + random() * 5.2;
    const yy = -1.4 - random() * 3.2 - length * 0.35;
    const x = Math.cos(a) * rr;
    const z = Math.sin(a) * rr * 0.9;
    vineBlocks.push({ p: [x, yy, z], s: [0.07, length, 0.07], r: [0, a, 0], c: i % 3 ? 0x34553b : 0x557342 });
    for (let k = 0; k < 3; k++) {
      vineBlocks.push({ p: [x + Math.cos(a + k) * 0.18, yy - length * (0.28 + k * 0.22), z + Math.sin(a + k) * 0.18], s: [0.32, 0.06, 0.13], r: [0, a + k, 0.3], c: 0x4f7044 });
    }
  }
  instancedBoxes(islandTop, materials.leaf, vineBlocks, '垂挂藤蔓');

  const stalBlocks = [];
  for (let i = 0; i < 28; i++) {
    const a = random() * TAU;
    const rr = 1.5 + random() * 5;
    const yy = -11.6 - random() * 1.2;
    const h = 1.2 + random() * 4.3;
    stalBlocks.push({ p: [Math.cos(a) * rr, yy - h * 0.5, Math.sin(a) * rr], s: [0.28 + random() * 0.42, h, 0.28 + random() * 0.42], r: [0, a, 0], c: [0x263136, 0x3d4748, 0x50544c][i % 3] });
  }
  instancedBoxes(islandTop, materials.basalt, stalBlocks, '倒锥钟乳岩体');

  // Courtyard paving and garden terraces.
  const courtyard = addCyl(islandTop, materials.stone, 8.2, 8.35, 0.26, 8, [0, 0.79, 0]);
  courtyard.rotation.y = Math.PI / 8;
  const pathMat = mat(0xb4ab92, { map: stoneTex, roughness: 0.88 });
  const pathBlocks = [];
  for (let z = -6.7; z <= 6.7; z += 0.72) {
    for (let x = -5.6; x <= 5.6; x += 0.72) {
      if (Math.abs(x) < 0.42 || Math.abs(z) < 0.42) continue;
      if (x * x + z * z > 39) continue;
      if ((Math.abs(x) < 4.8 && Math.abs(z) < 4.8) || (Math.abs(x - 5.7) < 1.5 && Math.abs(z) < 2.5)) continue;
      pathBlocks.push({ p: [x, 0.94 + (random() - 0.5) * 0.025, z], s: [0.64, 0.09, 0.64], c: [0xb7ad94, 0x9e9786, 0xd0c5a7][Math.floor(random() * 3)] });
    }
  }
  instancedBoxes(islandTop, pathMat, pathBlocks, '青石庭院铺地');

  // Pond, lotus leaves, lotus flowers, water lilies.
  const pond = new T.Group();
  pond.name = '莲花放生池';
  pond.position.set(5.7, 0.91, 2.0);
  islandTop.add(pond);
  addCyl(pond, materials.water, 2.15, 2.15, 0.12, 20, [0, 0, 0]);
  addCyl(pond, materials.white, 2.5, 2.5, 0.22, 20, [0, -0.05, 0]);
  for (let i = 0; i < 20; i++) {
    const a = i / 20 * TAU;
    addBox(pond, materials.white, [0.11, 0.55, 0.11], [Math.cos(a) * 2.42, 0.25, Math.sin(a) * 2.42]);
  }
  const lotusLeaves = [];
  const lotusFlowers = [];
  for (let i = 0; i < 24; i++) {
    const a = random() * TAU;
    const rr = random() * 1.8;
    lotusLeaves.push({ p: [Math.cos(a) * rr, 0.1 + random() * 0.1, Math.sin(a) * rr], s: [0.32 + random() * 0.25, 0.025, 0.3 + random() * 0.3], r: [0, random() * TAU, 0], c: i % 2 ? 0x3f754b : 0x6f974f });
    if (i % 3 === 0) {
      const ca = random() * TAU;
      lotusFlowers.push({ p: [Math.cos(ca) * (0.6 + random()), 0.3, Math.sin(ca) * (0.6 + random())], s: [0.19, 0.16, 0.19], c: [0xf2a0b5, 0xf8e9e9, 0xe87999][i % 3] });
    }
  }
  instancedBoxes(pond, materials.leaf, lotusLeaves, '荷叶');
  instancedBoxes(pond, materials.lotus, lotusFlowers, '莲花');

  // Pagoda. All architectural parts are procedural, using fine voxel-like courses.
  const pagoda = mkGroup('pagoda', root, 'pagoda');
  const pagodaBase = mkGroup('pagodaBase', pagoda, 'pagodaBase');
  const pagodaBody = mkGroup('pagodaBody', pagoda, 'pagodaBody');
  const pagodaFinial = mkGroup('pagodaFinial', pagoda, 'pagodaFinial');

  // Sumeru pedestal with waist, lotus carvings, corner posts and stairways.
  addCyl(pagodaBase, materials.stone, 5.0, 5.35, 0.52, 8, [0, 1.12, 0], [0, Math.PI / 8, 0]);
  addCyl(pagodaBase, materials.white, 4.62, 4.92, 0.48, 8, [0, 1.6, 0], [0, Math.PI / 8, 0]);
  addCyl(pagodaBase, materials.darkStone, 4.25, 4.38, 0.62, 8, [0, 2.14, 0], [0, Math.PI / 8, 0]);
  addCyl(pagodaBase, materials.stone, 4.65, 4.25, 0.38, 8, [0, 2.64, 0], [0, Math.PI / 8, 0]);
  addCyl(pagodaBase, materials.white, 4.8, 4.68, 0.2, 8, [0, 2.93, 0], [0, Math.PI / 8, 0]);
  for (let i = 0; i < 32; i++) {
    const a = i / 32 * TAU;
    const rr = 4.52;
    addBox(pagodaBase, materials.white, [0.26, 0.28, 0.2], [Math.cos(a) * rr, 2.2, Math.sin(a) * rr], [0, -a, 0.04]);
  }
  // Balustrades around the octagonal platform.
  for (let i = 0; i < 8; i++) {
    const a = i / 8 * TAU + Math.PI / 8;
    const nx = Math.cos(a), nz = Math.sin(a);
    const tx = -Math.sin(a), tz = Math.cos(a);
    const cx = nx * 4.4, cz = nz * 4.4;
    for (let j = -2; j <= 2; j++) {
      addBox(pagodaBase, materials.white, [0.14, 0.74, 0.14], [cx + tx * j * 0.72, 3.39, cz + tz * j * 0.72]);
      if (j < 2) {
        addBox(pagodaBase, materials.white, [0.82, 0.24, 0.08], [cx + tx * (j + 0.5) * 0.72, 3.2, cz + tz * (j + 0.5) * 0.72], [0, -a, 0]);
      }
    }
    addBox(pagodaBase, materials.white, [1.65, 0.08, 0.1], [cx, 3.72, cz], [0, -a, 0]);
  }
  // Four staircases.
  for (let d = 0; d < 4; d++) {
    const a = d / 4 * TAU;
    const dirX = Math.cos(a), dirZ = Math.sin(a);
    for (let s = 0; s < 7; s++) {
      const dist = 5.65 - s * 0.37;
      addBox(pagodaBase, materials.stone, [1.32, 0.17, 0.43], [dirX * dist, 1.13 + s * 0.16, dirZ * dist], [0, -a, 0]);
    }
  }

  const instancedCylinders = (parent, material, list, name = 'cylinders') => {
    if (!list.length) return null;
    const geo = new T.CylinderGeometry(1, 1, 1, 6);
    const tinted = list.some((it) => it.c !== undefined);
    const matInst = tinted && material.color ? material.clone() : material;
    if (matInst !== material) matInst.color.set(0xffffff);
    const inst = new T.InstancedMesh(geo, matInst, list.length);
    inst.name = name;
    const o = new T.Object3D();
    const c = new T.Color();
    list.forEach((it, i) => {
      o.position.set(it.p[0], it.p[1], it.p[2]);
      o.rotation.set(it.r?.[0] || 0, it.r?.[1] || 0, it.r?.[2] || 0);
      o.scale.set(it.s[0], it.s[1], it.s[2]);
      o.updateMatrix();
      inst.setMatrixAt(i, o.matrix);
      if (it.c !== undefined) { c.set(it.c); inst.setColorAt(i, c); }
    });
    inst.instanceMatrix.needsUpdate = true;
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
    inst.castShadow = list.length > 30;
    inst.receiveShadow = true;
    inst.computeBoundingSphere();
    parent.add(inst);
    return inst;
  };

  // Main body: seven octagonal storeys with a tapering profile.
  const tiers = 7;
  const baseTierR = 4.05;
  let tierY = 3.08;
  const tierData = [];
  for (let level = 0; level < tiers; level++) {
    const t = level / (tiers - 1);
    const radius = baseTierR * Math.pow(0.86, level) * (1 - 0.04 * t);
    const bodyH = 2.45 * Math.pow(0.965, level);
    const wallH = bodyH * 0.66;
    const eaveY = tierY + bodyH * 0.74;
    const g = new T.Group();
    g.name = '第' + (level + 1) + '层塔身';
    pagodaBody.add(g);
    tierData.push({ radius, y: tierY, bodyH, wallH, eaveY, group: g });

    // octagonal wall drum, rendered in small plaster courses
    const drum = new T.Mesh(new T.CylinderGeometry(radius, radius * 1.008, wallH, 8, 1), materials.plaster);
    drum.position.set(0, tierY + wallH / 2, 0);
    drum.rotation.y = Math.PI / 8;
    drum.castShadow = drum.receiveShadow = true;
    g.add(drum);

    // wall micro-voxel courses and columns at every octagon corner
    const wallVox = [];
    const columnList = [];
    for (let k = 0; k < 8; k++) {
      const a = k / 8 * TAU + Math.PI / 8;
      const nx = Math.cos(a), nz = Math.sin(a);
      columnList.push({ p: [nx * (radius - 0.06), tierY + wallH / 2, nz * (radius - 0.06)], s: [0.13, wallH + 0.24, 0.13] });
      for (let row = 0; row < 5; row++) {
        for (let col = -2; col <= 2; col++) {
          const aa = a + col * 0.073;
          wallVox.push({ p: [Math.cos(aa) * (radius + 0.035), tierY + 0.16 + row * 0.34, Math.sin(aa) * (radius + 0.035)], s: [0.34, 0.25, 0.07], r: [0, -aa, 0], c: [0xe5ddc7, 0xd9d0ba, 0xf1e8d0][(row + col + 8) % 3] });
        }
      }
      // columns / corner posts
      addBox(g, materials.woodDark, [0.58, 0.18, 0.58], [nx * (radius - 0.06), tierY + 0.08, nz * (radius - 0.06)], [0, -a, 0]);
      // lintel
      addBox(g, materials.wood, [radius * 0.55, 0.18, 0.16], [nx * (radius + 0.01), tierY + wallH - 0.15, nz * (radius + 0.01)], [0, -a + Math.PI / 2, 0]);
    }
    instancedBoxes(g, materials.plaster, wallVox, '白墙微体素砌层');
    instancedCylinders(g, materials.wood, columnList, '朱漆立柱');

    // front face arched doorway; other faces get slit windows
    const faceOffset = Math.PI / 8;
    for (let face = 0; face < 8; face++) {
      const a = face / 8 * TAU + faceOffset;
      const nx = Math.cos(a), nz = Math.sin(a);
      const tangent = new T.Vector3(-nz, 0, nx);
      const facePos = new T.Vector3(nx * (radius + 0.035), 0, nz * (radius + 0.035));
      if (face === 0 || face === 4) {
        const arch = new T.Shape();
        const w = Math.min(0.72, radius * 0.23);
        arch.moveTo(-w, 0);
        arch.lineTo(-w, wallH * 0.47);
        arch.quadraticCurveTo(-w, wallH * 0.73, 0, wallH * 0.76);
        arch.quadraticCurveTo(w, wallH * 0.73, w, wallH * 0.47);
        arch.lineTo(w, 0);
        arch.closePath();
        const hole = new T.Mesh(new T.ShapeGeometry(arch, 5), materials.woodDark);
        hole.position.set(facePos.x, tierY + 0.05, facePos.z);
        hole.rotation.y = -a + Math.PI / 2;
        g.add(hole);
        const doorGlow = new T.Sprite(materials.glow.clone());
        doorGlow.material.opacity = 0.24;
        doorGlow.position.set(facePos.x * 0.88, tierY + wallH * 0.45, facePos.z * 0.88);
        doorGlow.scale.setScalar(1.15 + level * 0.045);
        doorGlow.userData.ownMaterial = true;
        g.add(doorGlow);
        animated.glowSprites.push({ light: doorGlow, base: 1.2 + level * 0.08 });
        // door studs
        for (let q = 0; q < 8; q++) addBox(g, materials.gold, [0.06, 0.06, 0.06], [facePos.x + tangent.x * (q % 2 ? 0.3 : -0.3), tierY + 0.4 + Math.floor(q / 2) * 0.37, facePos.z + tangent.z * (q % 2 ? 0.3 : -0.3)]);
      } else {
        // lattice window: frame and grid
        const ww = Math.min(0.7, radius * 0.27);
        const wh = wallH * 0.36;
        addBox(g, materials.wood, [ww, 0.07, 0.08], [facePos.x, tierY + wallH * 0.58, facePos.z], [0, -a + Math.PI / 2, 0]);
        for (let col = -1; col <= 1; col++) {
          addBox(g, materials.wood, [0.045, wh, 0.045], [facePos.x + tangent.x * col * ww * 0.32, tierY + wallH * 0.58, facePos.z + tangent.z * col * ww * 0.32], [0, 0, 0]);
        }
        for (let row = -1; row <= 1; row++) {
          addBox(g, materials.wood, [ww * 0.9, 0.035, 0.04], [facePos.x, tierY + wallH * 0.58 + row * wh * 0.3, facePos.z], [0, -a + Math.PI / 2, 0]);
        }
      }
    }

    // dougong brackets: dou blocks + three-sheng arms + angled cantilever
    const bracketVox = [];
    for (let side = 0; side < 8; side++) {
      const a = side / 8 * TAU + faceOffset;
      const nx = Math.cos(a), nz = Math.sin(a);
      const tangent = new T.Vector3(-nz, 0, nx);
      const rr = radius - 0.03;
      for (let k = -2; k <= 2; k++) {
        const p = [nx * rr + tangent.x * k * 0.35, tierY + wallH + 0.08, nz * rr + tangent.z * k * 0.35];
        bracketVox.push({ p, s: [0.2, 0.2, 0.2], r: [0, -a, 0], c: k % 2 ? 0x8e3b2b : 0xb64b31 });
        bracketVox.push({ p: [p[0] + nx * 0.18, p[1] + 0.18, p[2] + nz * 0.18], s: [0.38, 0.1, 0.1], r: [0, -a, 0], c: 0x743126 });
      }
      for (let layer = 0; layer < 3; layer++) {
        const rr2 = radius + 0.15 + layer * 0.17;
        for (let k = -2; k <= 2; k++) {
          const aa = a + k * 0.025;
          bracketVox.push({ p: [Math.cos(aa) * rr2, tierY + wallH + 0.22 + layer * 0.12, Math.sin(aa) * rr2], s: [0.14, 0.12, 0.34], r: [0, -aa, 0], c: layer === 2 ? 0xc45b37 : 0x9f3f2d });
        }
      }
    }
    instancedBoxes(g, materials.wood, bracketVox, '斗拱与升');

    // broad roof with upturned corners. Sloped voxel tiles form a double-layer eave.
    const roof = new T.Group();
    roof.name = '飞檐';
    g.add(roof);
    const eaveR = radius + 1.18;
    const roofVox = [];
    const tileVox = [];
    const eaveEdge = [];
    const radialRows = 4;
    for (let side = 0; side < 8; side++) {
      const a0 = side / 8 * TAU + faceOffset;
      const half = Math.PI / 8;
      for (let row = 0; row < radialRows; row++) {
        const rr = radius * 0.68 + row * (eaveR - radius * 0.68) / radialRows;
        const yy = eaveY + 0.38 - row * 0.13;
        for (let col = -7; col <= 7; col++) {
          const a = a0 + col / 7 * half * 0.92;
          const x = Math.cos(a) * rr;
          const z = Math.sin(a) * rr;
          const lift = Math.pow(Math.abs(col) / 7, 3) * 0.36;
          roofVox.push({ p: [x, yy + lift, z], s: [0.31, 0.12, 0.34], r: [0.08, -a, -Math.sign(col) * 0.08], c: (col + side + row) % 3 === 0 ? 0x3f5757 : 0x314649 });
          if (row >= radialRows - 1) tileVox.push({ p: [x, yy + lift + 0.05, z], s: [0.19, 0.16, 0.35], r: [0.1, -a, 0], c: (col % 2 ? 0x4f6460 : 0x293c3f) });
        }
      }
      // eave fascia and corner ridge/upturn
      for (let col = -8; col <= 8; col++) {
        const aa = a0 + col / 8 * half * 0.98;
        const rr = eaveR + 0.04;
        const lift = Math.pow(Math.abs(col) / 8, 3) * 0.62;
        eaveEdge.push({ p: [Math.cos(aa) * rr, eaveY - 0.12 + lift, Math.sin(aa) * rr], s: [0.27, 0.2, 0.22], r: [0, -aa, -Math.sign(col) * 0.16], c: 0x50615d });
      }
      // upturned corner spur
      const a = a0 + half;
      const rr = eaveR;
      const tip = new T.Vector3(Math.cos(a) * (rr + 0.72), eaveY + 0.36, Math.sin(a) * (rr + 0.72));
      lineBetween(new T.Vector3(Math.cos(a) * (rr - 0.18), eaveY - 0.02, Math.sin(a) * (rr - 0.18)), tip, 0.11, materials.roofEdge, roof);
      addBox(roof, materials.roof, [0.18, 0.22, 0.18], [tip.x, tip.y, tip.z], [0, -a, -0.35]);
      // eave bell under corner
      const bell = new T.Group();
      bell.position.set(tip.x * 0.97, eaveY - 0.36, tip.z * 0.97);
      roof.add(bell);
      addCyl(bell, materials.gold, 0.05, 0.14, 0.18, 8, [0, 0, 0]);
      addSphere(bell, materials.goldBright, 0.07, 0, [0, -0.14, 0]);
      animated.spinners.push({ obj: bell, axis: 'y', speed: 0.1 + random() * 0.15 });
    }
    instancedBoxes(roof, materials.roof, roofVox, '瓦垄微体素');
    instancedBoxes(roof, materials.roofEdge, tileVox, '檐口筒瓦');
    instancedBoxes(roof, materials.roofEdge, eaveEdge, '檐口封边');

    // small ridge beasts on four cardinal ridges
    for (let b = 0; b < 4; b++) {
      const a = b / 4 * TAU + faceOffset;
      const rr = eaveR - 0.15;
      const beast = new T.Group();
      beast.position.set(Math.cos(a) * rr, eaveY + 0.42, Math.sin(a) * rr);
      beast.rotation.y = -a + Math.PI / 2;
      roof.add(beast);
      addBox(beast, materials.roofEdge, [0.18, 0.16, 0.3], [0, 0, 0]);
      addBox(beast, materials.roofEdge, [0.14, 0.16, 0.14], [0, 0.14, 0.1]);
      addBox(beast, materials.roofEdge, [0.06, 0.11, 0.06], [-0.08, 0.24, 0.1]);
      addBox(beast, materials.roofEdge, [0.06, 0.11, 0.06], [0.08, 0.24, 0.1]);
    }
    tierY = eaveY + bodyH * 0.25;
  }

  // Finial: gilded bottle, rings, canopy, moon and jewel.
  const top = tierData[tierData.length - 1];
  const finialBaseY = top.y + top.bodyH + 0.72;
  addCyl(pagodaFinial, materials.roof, 1.12, 1.55, 0.34, 8, [0, finialBaseY, 0]);
  addCyl(pagodaFinial, materials.gold, 0.25, 0.42, 0.48, 10, [0, finialBaseY + 0.42, 0]);
  addSphere(pagodaFinial, materials.goldBright, 0.38, 1, [0, finialBaseY + 0.82, 0], [1, 0.75, 1]);
  addCyl(pagodaFinial, materials.gold, 0.08, 0.15, 1.55, 8, [0, finialBaseY + 1.75, 0]);
  for (let i = 0; i < 5; i++) {
    addCyl(pagodaFinial, materials.gold, 0.35 - i * 0.04, 0.45 - i * 0.045, 0.09, 12, [0, finialBaseY + 1.25 + i * 0.22, 0]);
  }
  addCyl(pagodaFinial, materials.goldBright, 0.52, 0.08, 0.09, 16, [0, finialBaseY + 2.5, 0]);
  addSphere(pagodaFinial, materials.goldBright, 0.25, 1, [0, finialBaseY + 2.78, 0]);
  addCyl(pagodaFinial, materials.gold, 0.035, 0.12, 0.65, 8, [0, finialBaseY + 3.1, 0]);
  addSphere(pagodaFinial, materials.goldBright, 0.13, 1, [0, finialBaseY + 3.48, 0]);

  const finialGlow = new T.Sprite(materials.glow.clone());
  finialGlow.position.set(0, finialBaseY + 0.82, 0);
  finialGlow.scale.setScalar(2.1);
  finialGlow.material.opacity = 0.18;
  pagodaFinial.add(finialGlow);
  animated.glowSprites.push({ light: finialGlow, base: 1.35 });

  // Vegetation: pines, blossom trees, ginkgo, peonies and Taihu rocks.
  const vegetation = mkGroup('vegetation', root, 'vegetation');
  const treeGroups = [];
  function pineTree(x, z, scale = 1, hue = 0) {
    const g = new T.Group();
    g.position.set(x, 0.92, z);
    g.scale.setScalar(scale);
    vegetation.add(g);
    const trunkMat = materials.woodDark;
    addCyl(g, trunkMat, 0.16, 0.32, 2.2, 6, [0, 1.05, 0], [0.05, 0, -0.12]);
    const branches = [
      [-0.6, 2.2, 0.1, 0.95, 0.2], [0.55, 2.6, -0.2, 0.85, -0.28],
      [-0.25, 3.0, 0.35, 1.1, 0.05], [0.35, 3.35, 0.2, 0.8, 0.35],
    ];
    for (let i = 0; i < branches.length; i++) {
      const b = branches[i];
      const end = new T.Vector3(b[0], b[1], b[2]);
      lineBetween(new T.Vector3(0, 0.7 + i * 0.35, 0), end, 0.1, trunkMat, g);
      const needleVox = [];
      for (let k = 0; k < 10; k++) {
        needleVox.push({ p: [end.x + (random() - 0.5) * b[3], end.y + (random() - 0.3) * 0.42, end.z + (random() - 0.5) * b[3]], s: [0.35 + random() * 0.25, 0.12 + random() * 0.2, 0.35 + random() * 0.25], r: [0, random() * 2, 0], c: [0x244a36, 0x38654a, 0x55774b][k % 3] });
      }
      instancedBoxes(g, hue ? materials.pineLight : materials.pine, needleVox, '松针体素');
    }
    treeGroups.push(g);
    return g;
  }
  function blossomTree(x, z, scale = 1, kind = 'pink') {
    const g = new T.Group();
    g.position.set(x, 0.92, z);
    g.scale.setScalar(scale);
    vegetation.add(g);
    const trunk = new T.Group();
    trunk.rotation.z = (random() - 0.5) * 0.22;
    g.add(trunk);
    addCyl(trunk, materials.woodDark, 0.15, 0.28, 2.3, 6, [0, 1.05, 0]);
    const branchEnds = [[-0.9, 2.7, 0.2], [0.8, 2.9, 0.3], [0.1, 3.4, -0.3], [-0.3, 3.1, -0.8], [0.45, 3.5, -0.4]];
    for (let i = 0; i < branchEnds.length; i++) {
      const end = new T.Vector3(...branchEnds[i]);
      lineBetween(new T.Vector3(0, 1.2 + i * 0.17, 0), end, 0.09, materials.woodDark, trunk);
    }
    const bloomVox = [];
    const pal = kind === 'gold' ? [0xd7a52d, 0xf0c451, 0xa67822] : [0xf1a0ad, 0xf6bec4, 0xdb6e8b];
    for (let i = 0; i < 100; i++) {
      const e = branchEnds[i % branchEnds.length];
      bloomVox.push({ p: [e[0] + (random() - 0.5) * 1.55, e[1] + (random() - 0.35) * 1.15, e[2] + (random() - 0.5) * 1.35], s: [0.25 + random() * 0.34, 0.18 + random() * 0.28, 0.25 + random() * 0.34], r: [random(), random(), random()], c: pal[i % pal.length] });
    }
    instancedBoxes(g, kind === 'gold' ? materials.ginkgo : materials.blossom, bloomVox, '花冠体素');
    treeGroups.push(g);
    return g;
  }
  pineTree(-6.7, -2.1, 1.15, 1);
  pineTree(6.2, -3.6, 0.95, 0);
  pineTree(-3.0, 6.7, 0.8, 0);
  blossomTree(2.8, -6.1, 1.0, 'pink');
  blossomTree(-6.4, 4.5, 0.82, 'pink');
  blossomTree(5.8, 5.8, 0.72, 'gold');

  const peonyBeds = [];
  for (let i = 0; i < 180; i++) {
    const a = random() * TAU;
    const rr = 4.9 + random() * 3.4;
    const x = Math.cos(a) * rr;
    const z = Math.sin(a) * rr;
    if (x > 3.2 && x < 8.2 && z > -0.2 && z < 4.5) continue;
    const c = [0xd72d50, 0xf07791, 0xb13a6e, 0xf2e1d6, 0xe7b63f][i % 5];
    peonyBeds.push({ p: [x, 1.04 + random() * 0.22, z], s: [0.18 + random() * 0.2, 0.12 + random() * 0.18, 0.18 + random() * 0.2], r: [0, random() * TAU, 0], c });
    if (i % 4 === 0) peonyBeds.push({ p: [x, 0.95, z], s: [0.34, 0.08, 0.34], r: [0, random() * TAU, 0], c: 0x315c3d });
  }
  instancedBoxes(vegetation, mat(0xffffff, { roughness: 0.88 }), peonyBeds, '洛阳牡丹花坛');

  // Taihu rocks with porous micro-voxel silhouettes.
  const rockForms = [];
  for (let n = 0; n < 5; n++) {
    const bx = -4.5 + n * 2.1, bz = 5.5 - (n % 2) * 1.2;
    for (let i = 0; i < 16; i++) {
      rockForms.push({ p: [bx + (random() - 0.5) * 1.1, 1.1 + random() * 1.4, bz + (random() - 0.5) * 0.8], s: [0.18 + random() * 0.28, 0.18 + random() * 0.34, 0.18 + random() * 0.25], r: [random(), random(), random()], c: [0x757a71, 0x9a9a8b, 0x575e59][i % 3] });
    }
  }
  instancedBoxes(vegetation, materials.rock, rockForms, '太湖石');

  // Tang pavilion and covered corridor.
  const pavilion = new T.Group();
  pavilion.name = '唐代八角凉亭';
  pavilion.position.set(-6.2, 0.9, 5.6);
  vegetation.add(pavilion);
  addCyl(pavilion, materials.stone, 1.45, 1.55, 0.22, 8, [0, 0.11, 0]);
  for (let i = 0; i < 8; i++) {
    const a = i / 8 * TAU + Math.PI / 8;
    addCyl(pavilion, materials.wood, 0.07, 0.09, 1.95, 6, [Math.cos(a) * 1.08, 1.15, Math.sin(a) * 1.08]);
  }
  addCyl(pavilion, materials.wood, 1.32, 1.35, 0.18, 8, [0, 2.14, 0], [0, Math.PI / 8, 0]);
  const pavilionRoofVox = [];
  for (let side = 0; side < 8; side++) {
    const a = side / 8 * TAU;
    for (let row = 0; row < 5; row++) {
      const rr = 1.52 - row * 0.23;
      for (let col = -4; col <= 4; col++) {
        const aa = a + col / 4 * Math.PI / 8;
        pavilionRoofVox.push({ p: [Math.cos(aa) * rr, 2.55 - row * 0.19, Math.sin(aa) * rr], s: [0.25, 0.11, 0.28], r: [0.1, -aa, 0], c: (row + col) % 2 ? 0x34494b : 0x53635d });
      }
    }
  }
  instancedBoxes(pavilion, materials.roof, pavilionRoofVox, '凉亭屋面');
  addSphere(pavilion, materials.gold, 0.12, 1, [0, 3.35, 0]);
  // corridor
  const corridor = new T.Group();
  corridor.position.set(-5.4, 0.9, -5.5);
  corridor.rotation.y = -0.35;
  vegetation.add(corridor);
  for (let i = 0; i < 5; i++) {
    const x = -2.2 + i * 1.1;
    addCyl(corridor, materials.wood, 0.09, 0.12, 1.7, 6, [x, 0.9, 0.65]);
    addCyl(corridor, materials.wood, 0.09, 0.12, 1.7, 6, [x, 0.9, -0.65]);
  }
  addBox(corridor, materials.roof, [5.8, 0.18, 1.9], [0.1, 1.84, 0], [0, 0, -0.04]);
  for (let i = 0; i < 7; i++) addBox(corridor, materials.wood, [0.75, 0.1, 0.1], [-2.2 + i * 0.75, 1.98, 0.65], [0, 0, 0]);

  // Stone lanterns and sutra pillar.
  function stoneLantern(x, z, scale = 1) {
    const g = new T.Group();
    g.position.set(x, 0.9, z);
    g.scale.setScalar(scale);
    vegetation.add(g);
    addCyl(g, materials.stone, 0.25, 0.38, 0.22, 6, [0, 0.11, 0]);
    addCyl(g, materials.stone, 0.14, 0.2, 0.75, 6, [0, 0.55, 0]);
    addCyl(g, materials.stone, 0.35, 0.25, 0.16, 6, [0, 1.0, 0]);
    addBox(g, materials.white, [0.3, 0.36, 0.3], [0, 1.25, 0]);
    const roofVox = [];
    for (let i = 0; i < 12; i++) {
      const a = i / 12 * TAU;
      roofVox.push({ p: [Math.cos(a) * 0.34, 1.52 + Math.cos(a * 2) * 0.05, Math.sin(a) * 0.34], s: [0.2, 0.08, 0.24], r: [0, -a, 0], c: 0x4e5c57 });
    }
    instancedBoxes(g, materials.roof, roofVox, '石灯顶');
    addSphere(g, materials.stone, 0.07, 0, [0, 1.72, 0]);
    const glow = new T.Sprite(materials.glow.clone());
    glow.material.opacity = 0.25;
    glow.position.set(0, 1.27, 0);
    glow.scale.setScalar(0.48);
    g.add(glow);
  }
  stoneLantern(2.9, 6.3, 0.75);
  stoneLantern(-2.4, 6.2, 0.62);
  stoneLantern(7.7, 0.3, 0.66);
  // sutra pillar
  const sutra = new T.Group();
  sutra.position.set(-2.2, 0.9, 6.7);
  vegetation.add(sutra);
  addCyl(sutra, materials.stone, 0.38, 0.5, 0.18, 8, [0, 0.09, 0]);
  addCyl(sutra, materials.stone, 0.15, 0.2, 1.8, 8, [0, 1.0, 0]);
  for (let i = 0; i < 4; i++) addBox(sutra, materials.stone, [0.38, 0.3, 0.08], [0, 0.45 + i * 0.36, 0.16], [0, 0, 0]);
  addCyl(sutra, materials.stone, 0.35, 0.16, 0.2, 8, [0, 1.97, 0]);
  addSphere(sutra, materials.stone, 0.12, 0, [0, 2.15, 0]);

  // Waterfalls and pond stream. Points are animated by shader-free CPU buffer.
  const waterfalls = mkGroup('waterfalls', root, 'waterfalls');
  const waterfallDefs = [
    { a: 0.3, r: 8.5, w: 1.15, h: 8.8, tilt: 0.08 },
    { a: 1.2, r: 10.1, w: 0.72, h: 11.3, tilt: -0.12 },
    { a: 2.7, r: 9.7, w: 0.88, h: 10.2, tilt: 0.15 },
  ];
  for (let wi = 0; wi < waterfallDefs.length; wi++) {
    const d = waterfallDefs[wi];
    const x = Math.cos(d.a) * d.r;
    const z = Math.sin(d.a) * d.r * 0.9;
    const w = d.w;
    const geo = new T.PlaneGeometry(w, d.h, 1, 8);
    const wm = materials.water.clone();
    animated.localMaterials.push(wm);
    wm.opacity = 0.62 + wi * 0.05;
    const fall = new T.Mesh(geo, wm);
    fall.position.set(x, 0.8 - d.h / 2, z);
    fall.rotation.y = -d.a + Math.PI / 2;
    fall.rotation.z = d.tilt;
    fall.castShadow = false;
    waterfalls.add(fall);
    const drops = [];
    for (let i = 0; i < 28; i++) {
      const drop = new T.Object3D();
      drop.position.set(x + (random() - 0.5) * w, 0.6 - random() * d.h, z + (random() - 0.5) * 0.22);
      drop.userData.seed = random();
      drop.userData.baseX = drop.position.x;
      drop.userData.baseZ = drop.position.z;
      drop.userData.speed = 0.5 + random();
      drop.userData.floor = 0.8 - d.h;
      drop.updateMatrix();
      drops.push(drop);
    }
    const dropGeo = new T.BoxGeometry(0.07, 0.28, 0.07);
    const dropMesh = new T.InstancedMesh(dropGeo, materials.foam, drops.length);
    dropMesh.name = '瀑布水沫';
    dropMesh.castShadow = false;
    dropMesh.frustumCulled = false;
    dropMesh.userData.drops = drops;
    drops.forEach((d, i) => dropMesh.setMatrixAt(i, d.matrix));
    dropMesh.instanceMatrix.needsUpdate = true;
    waterfalls.add(dropMesh);
    animated.waterfallMists.push({ drops, fall, dropMesh, baseOpacity: wm.opacity });
    // mist at lip
    for (let i = 0; i < 5; i++) {
      const spr = new T.Sprite(materials.glow.clone());
      spr.material.color.set(0xd7f4f3);
      spr.material.opacity = 0.08;
      spr.position.set(x + (random() - 0.5) * w * 2, 0.65 - random() * 0.4, z + (random() - 0.5) * 0.5);
      spr.scale.set(1.5, 0.5, 1);
      waterfalls.add(spr);
    }
  }
  // water rill from pond to edge
  const streamCurve = new T.CatmullRomCurve3([
    new T.Vector3(5.7, 0.91, 2.0), new T.Vector3(7.4, 0.92, 0.8),
    new T.Vector3(9.0, 0.93, -0.2), new T.Vector3(10.1, 0.93, -1.5),
  ]);
  const stream = new T.Mesh(new T.TubeGeometry(streamCurve, 18, 0.26, 5, false), materials.water);
  stream.rotation.x = 0;
  stream.castShadow = false;
  islandTop.add(stream);

  // Satellite islands.
  const satellites = mkGroup('satellites', root, 'satellites');
  satellites.userData.dynamic = true;
  const satDefs = [
    { x: -18, y: 4.2, z: -6.5, r: 2.6, seed: 1 },
    { x: 17, y: 7.0, z: 3.5, r: 2.0, seed: 2 },
    { x: 13, y: -5.0, z: -15, r: 3.2, seed: 3 },
    { x: -11, y: -7.3, z: 14, r: 2.25, seed: 4 },
    { x: 20, y: -8.2, z: 13, r: 1.5, seed: 5 },
    { x: -24, y: 10.5, z: 6, r: 1.1, seed: 6 },
  ];
  for (let si = 0; si < satDefs.length; si++) {
    const d = satDefs[si];
    const g = new T.Group();
    g.position.set(d.x, d.y, d.z);
    g.rotation.y = d.seed * 0.7;
    satellites.add(g);
    addCyl(g, materials.grass, d.r, d.r * 0.82, 0.32, 7, [0, 0, 0]);
    addCyl(g, materials.earth, d.r * 0.84, d.r * 0.5, 1.1, 7, [0, -0.62, 0]);
    addCyl(g, materials.rock, d.r * 0.53, d.r * 0.08, 1.9, 6, [0, -1.62, 0]);
    const satBlocks = [];
    for (let i = 0; i < 11; i++) {
      const a = random() * TAU;
      const rr = random() * d.r * 0.55;
      satBlocks.push({ p: [Math.cos(a) * rr, 0.23 + random() * 0.15, Math.sin(a) * rr], s: [0.2 + random() * 0.3, 0.2 + random() * 0.3, 0.2 + random() * 0.3], c: [0x365f45, 0x66834f, 0x8a975c][i % 3] });
    }
    instancedBoxes(g, materials.leaf, satBlocks, '微型植被');
    if (si === 0 || si === 2) {
      addCyl(g, materials.stone, 0.2, 0.28, 1.2, 6, [0, 0.85, 0]);
      addBox(g, materials.stone, [0.58, 0.22, 0.15], [0, 1.46, 0]);
    }
    animated.floaters.push({ obj: g, baseY: d.y, phase: d.seed * 1.7, amp: 0.08 + d.seed * 0.006 });
  }

  boxesEnabled = false;
  // Chinese dragon: segmented micro-voxel body, antlers, whiskers, claws, fins.
  const dragon = mkGroup('dragon', root, 'dragon');
  dragon.userData.dynamic = true;
  const dragonPivot = new T.Group();
  dragon.add(dragonPivot);
  const dragonSegments = [];
  const segCount = 26;
  for (let i = 0; i < segCount; i++) {
    const seg = new T.Group();
    const t = i / (segCount - 1);
    const r = 0.25 * (1 - t * 0.6);
    dragonPivot.add(seg);
    const segMesh = new T.Mesh(new T.IcosahedronGeometry(r * 1.15, 0), i % 3 === 0 ? materials.dragonLight : materials.dragon);
    segMesh.scale.set(1.1, 0.86, 0.92);
    segMesh.castShadow = true;
    seg.add(segMesh);
    const scales = [];
    for (let s = 0; s < 5; s++) {
      const a = s / 5 * TAU + i * 0.4;
      scales.push({
        p: [Math.cos(a) * r * 0.72, Math.sin(a) * r * 0.62, 0.04],
        s: [0.09, 0.07, 0.19],
        r: [a * 0.3, a, 0.5],
        c: i % 4 === 0 ? 0xe8bd55 : 0x6bd0b5,
      });
    }
    instancedBoxes(seg, i % 4 === 0 ? materials.dragonGold : materials.dragonLight, scales, '龙鳞');
    if (i > 2 && i < 23 && i % 2 === 0) {
      const fin = new T.Mesh(new T.ConeGeometry(0.11, 0.44, 4), materials.dragonGold);
      fin.position.set(0, r + 0.1, -0.02);
      fin.rotation.x = -0.4;
      seg.add(fin);
    }
    if (i === 5 || i === 9 || i === 16) {
      for (let c = 0; c < 2; c++) {
        const leg = new T.Group();
        leg.position.set((c ? 1 : -1) * r, -r * 0.4, 0);
        seg.add(leg);
        lineBetween(new T.Vector3(0, 0, 0), new T.Vector3((c ? 1 : -1) * 0.22, -0.36, 0.15), 0.065, materials.dragon, leg);
        lineBetween(new T.Vector3((c ? 1 : -1) * 0.22, -0.36, 0.15), new T.Vector3((c ? 1 : -1) * 0.38, -0.45, 0.42), 0.055, materials.dragonGold, leg);
        for (let q = -1; q <= 1; q++) {
          lineBetween(new T.Vector3((c ? 1 : -1) * 0.36, -0.44, 0.38), new T.Vector3((c ? 1 : -1) * (0.44 + q * 0.05), -0.49, 0.56 + q * 0.06), 0.035, materials.dragonGold, leg);
        }
      }
    }
    dragonSegments.push(seg);
  }
  // head at first segment
  const head = dragonSegments[0];
  addSphere(head, materials.dragon, 0.38, 1, [0, 0, 0.28], [1.0, 0.9, 1.25]);
  addBox(head, materials.dragonLight, [0.46, 0.18, 0.58], [0, -0.12, 0.68]);
  addSphere(head, materials.goldBright, 0.06, 0, [-0.24, 0.12, 0.58]);
  addSphere(head, materials.goldBright, 0.06, 0, [0.24, 0.12, 0.58]);
  addSphere(head, materials.eye, 0.035, 0, [-0.26, 0.13, 0.61]);
  addSphere(head, materials.eye, 0.035, 0, [0.26, 0.13, 0.61]);
  // antlers
  for (const side of [-1, 1]) {
    const a = new T.Vector3(side * 0.2, 0.22, 0.25);
    const b = new T.Vector3(side * 0.42, 0.62, 0.18);
    const c = new T.Vector3(side * 0.55, 0.9, 0.05);
    lineBetween(a, b, 0.065, materials.dragonGold, head);
    lineBetween(b, c, 0.045, materials.dragonGold, head);
    lineBetween(b, new T.Vector3(side * 0.22, 0.78, 0.06), 0.035, materials.dragonGold, head);
    // whisker
    const curve = new T.CatmullRomCurve3([
      new T.Vector3(side * 0.22, -0.08, 0.78),
      new T.Vector3(side * 0.5, -0.1, 1.05),
      new T.Vector3(side * 0.65, 0.05, 1.25),
    ]);
    const w = new T.Mesh(new T.TubeGeometry(curve, 8, 0.018, 3, false), materials.goldBright);
    head.add(w);
  }
  // tail fan
  for (let i = 0; i < 7; i++) {
    const fin = new T.Mesh(new T.ConeGeometry(0.12, 0.65 - i * 0.04, 4), i % 2 ? materials.dragonGold : materials.dragonLight);
    fin.position.set((i - 3) * 0.07, 0.1 + Math.sin(i) * 0.08, -0.18 - i * 0.015);
    fin.rotation.set(0.7, 0, (i - 3) * 0.14);
    dragonSegments[segCount - 1].add(fin);
  }

  // Phoenix with jointed wings and ribbon tail.
  const phoenix = mkGroup('phoenix', root, 'phoenix');
  phoenix.userData.dynamic = true;
  const phoenixPivot = new T.Group();
  phoenix.add(phoenixPivot);
  const phoenixBody = new T.Group();
  phoenixPivot.add(phoenixBody);
  addSphere(phoenixBody, materials.phoenix, 0.36, 1, [0, 0, 0], [0.8, 0.75, 1.55]);
  addSphere(phoenixBody, materials.phoenixGold, 0.22, 1, [0, 0.3, 0.5]);
  addBox(phoenixBody, materials.phoenixOrange, [0.12, 0.18, 0.3], [0, 0.28, 0.72]);
  addSphere(phoenixBody, materials.eye, 0.025, 0, [-0.15, 0.35, 0.59]);
  addSphere(phoenixBody, materials.eye, 0.025, 0, [0.15, 0.35, 0.59]);
  for (let i = 0; i < 3; i++) {
    const crest = new T.Mesh(new T.ConeGeometry(0.035, 0.4 + i * 0.08, 4), materials.phoenixGold);
    crest.position.set((i - 1) * 0.08, 0.57 + i * 0.03, 0.45);
    crest.rotation.x = -0.45;
    phoenixBody.add(crest);
  }
  const wings = [];
  for (const side of [-1, 1]) {
    const shoulder = new T.Group();
    shoulder.position.set(side * 0.25, 0.05, 0.0);
    phoenixBody.add(shoulder);
    const upper = new T.Group();
    shoulder.add(upper);
    lineBetween(new T.Vector3(0, 0, 0), new T.Vector3(side * 0.8, 0.15, -0.12), 0.08, materials.phoenix, upper);
    const lower = new T.Group();
    lower.position.set(side * 0.75, 0.12, -0.1);
    upper.add(lower);
    lineBetween(new T.Vector3(0, 0, 0), new T.Vector3(side * 0.72, -0.08, 0.12), 0.06, materials.phoenixOrange, lower);
    const feathers = [];
    for (let i = 0; i < 8; i++) {
      feathers.push({
        p: [side * (0.12 + i * 0.09), -0.2 + i * 0.025, 0.05 + i * 0.07],
        s: [0.14, 0.58 - i * 0.03, 0.035],
        r: [0, side * 0.3, side * (0.35 + i * 0.08)],
        c: [0xee7a30, 0xf0c75e, 0x426d91][i % 3],
      });
    }
    instancedBoxes(lower, materials.phoenixOrange, feathers, '凤羽');
    wings.push({ shoulder, upper, lower, side });
  }
  const tail = [];
  for (let i = 0; i < 9; i++) {
    const t = new T.Group();
    t.position.set(0, -0.05, -0.45);
    t.rotation.y = (i - 4) * 0.16;
    t.rotation.x = -0.12 - Math.abs(i - 4) * 0.03;
    phoenixBody.add(t);
    const len = 1.3 + (4 - Math.abs(i - 4)) * 0.18;
    const feather = new T.Mesh(new T.BoxGeometry(0.07, 0.06, len), i % 3 === 0 ? materials.phoenixBlue : i % 2 ? materials.phoenixOrange : materials.phoenixGold);
    feather.position.set(0, 0, -len / 2);
    t.add(feather);
    tail.push(t);
  }

  // Cranes, petals, fireflies, clouds.
  const cranes = new T.Group();
  cranes.name = '白鹤群';
  cranes.userData.dynamic = true;
  root.add(cranes);
  const craneBirds = [];
  for (let i = 0; i < 9; i++) {
    const g = new T.Group();
    g.position.set(-14 + i * 3.1, 12 + (i % 3) * 1.7, -9 + (i % 2) * 6);
    g.rotation.y = i * 0.4;
    cranes.add(g);
    addSphere(g, materials.whiteBird, 0.18, 0, [0, 0, 0], [0.7, 0.55, 1.5]);
    addCyl(g, materials.whiteBird, 0.03, 0.045, 0.65, 4, [0, 0.04, 0.4], [0.6, 0, 0]);
    addCyl(g, materials.whiteBird, 0.06, 0.06, 0.12, 4, [0, 0.26, 0.7]);
    const wl = new T.Group();
    wl.position.set(-0.1, 0.08, 0.0);
    g.add(wl);
    lineBetween(new T.Vector3(), new T.Vector3(-0.65, 0.12, 0.15), 0.035, materials.whiteBird, wl);
    const wr = new T.Group();
    wr.position.set(0.1, 0.08, 0.0);
    g.add(wr);
    lineBetween(new T.Vector3(), new T.Vector3(0.65, 0.12, 0.15), 0.035, materials.whiteBird, wr);
    craneBirds.push({ obj: g, wl, wr, phase: i * 0.7, baseY: g.position.y });
  }

  const petalCount = 180;
  const petalGeo = new T.BufferGeometry();
  const petalPositions = new Float32Array(petalCount * 3);
  const petalColors = new Float32Array(petalCount * 3);
  const petalSeeds = [];
  for (let i = 0; i < petalCount; i++) {
    const x = (random() - 0.5) * 28;
    const y = 2 + random() * 18;
    const z = (random() - 0.5) * 28;
    petalPositions.set([x, y, z], i * 3);
    const c = new T.Color(i % 4 ? 0xf2a0b5 : 0xffe8e3);
    petalColors.set([c.r, c.g, c.b], i * 3);
    petalSeeds.push({ x, y, z, phase: random() * TAU, speed: 0.18 + random() * 0.35 });
  }
  petalGeo.setAttribute('position', new T.BufferAttribute(petalPositions, 3));
  petalGeo.setAttribute('color', new T.BufferAttribute(petalColors, 3));
  const petalMat = new T.PointsMaterial({ size: 0.09, map: materials.glow.map, vertexColors: true, transparent: true, opacity: 0.8, depthWrite: false, blending: T.AdditiveBlending });
  animated.localMaterials.push(petalMat);
  const petals = new T.Points(petalGeo, petalMat);
  petals.name = '飘落花瓣';
  root.add(petals);
  animated.petals = { points: petals, seeds: petalSeeds, geo: petalGeo };

  const fireflyCount = 70;
  const ffGeo = new T.BufferGeometry();
  const ffPos = new Float32Array(fireflyCount * 3);
  const ffSeeds = [];
  for (let i = 0; i < fireflyCount; i++) {
    const a = random() * TAU;
    const rr = 3 + random() * 9;
    const p = [Math.cos(a) * rr, 1.4 + random() * 4.2, Math.sin(a) * rr];
    ffPos.set(p, i * 3);
    ffSeeds.push({ p, phase: random() * TAU, speed: 0.3 + random() * 0.5 });
  }
  ffGeo.setAttribute('position', new T.BufferAttribute(ffPos, 3));
  const ffMat = new T.PointsMaterial({ color: 0xffdf7a, size: 0.14, map: materials.glow.map, transparent: true, opacity: 0.85, depthWrite: false, blending: T.AdditiveBlending });
  animated.localMaterials.push(ffMat);
  const fireflies = new T.Points(ffGeo, ffMat);
  root.add(fireflies);
  animated.fireflies = { points: fireflies, seeds: ffSeeds, geo: ffGeo };

  const clouds = mkGroup('clouds', root, 'clouds');
  clouds.userData.dynamic = true;
  const cloudMat = new T.MeshStandardMaterial({ color: 0xe9ece6, roughness: 1, transparent: true, opacity: 0.26, depthWrite: false });
  animated.localMaterials.push(cloudMat);
  const cloudGroups = [];
  for (let i = 0; i < 7; i++) {
    const g = new T.Group();
    const a = i / 7 * TAU + 0.2;
    g.position.set(Math.cos(a) * (14 + i * 1.6), -2.2 + (i % 3) * 2.5, Math.sin(a) * (14 + i * 1.6));
    g.rotation.y = a;
    clouds.add(g);
    const vox = [];
    for (let k = 0; k < 18; k++) {
      vox.push({ p: [(random() - 0.5) * 6.5, (random() - 0.5) * 0.7, (random() - 0.5) * 2.5], s: [1 + random() * 1.8, 0.35 + random() * 0.4, 0.8 + random() * 1.2], r: [0, random() * 0.4, 0], c: i % 2 ? 0xdbe1de : 0xf1eee1 });
    }
    instancedBoxes(g, cloudMat, vox, '体素云层');
    cloudGroups.push({ obj: g, base: g.position.clone(), phase: i });
  }

  flushBoxes();

  // Merge stationary meshes by material inside each named group. Keep animated
  // subtrees (creatures, bells, water droplets, clouds) untouched.
  const animatedRoots = new Set([
    dragon, phoenix, cranes, petals, fireflies, waterfalls, clouds,
    ...dragonSegments, ...wings.map((w) => w.shoulder),
  ]);
  const mergeCandidateRoots = [islandTop, pagoda, vegetation];
  function mergeStaticMeshes(group) {
    const buckets = new Map();
    const removals = [];
    const walk = (node) => {
      for (const child of [...node.children]) {
        if (!child.isMesh || child.isInstancedMesh) {
          if (child.isGroup) walk(child);
          continue;
        }
        let p = child.parent;
        let skip = false;
        while (p && p !== group) {
          if (animatedRoots.has(p)) { skip = true; break; }
          p = p.parent;
        }
        if (skip || animatedRoots.has(child)) continue;
        const key = child.material.uuid + ':' + (child.castShadow ? 1 : 0) + ':' + (child.receiveShadow ? 1 : 0);
        if (!buckets.has(key)) buckets.set(key, { material: child.material, castShadow: child.castShadow, receiveShadow: child.receiveShadow, meshes: [] });
        buckets.get(key).meshes.push(child);
      }
    };
    walk(group);
    for (const bucket of buckets.values()) {
      if (bucket.meshes.length < 3) continue;
      let merged = null;
      const geometries = [];
      try {
        for (const mesh of bucket.meshes) {
          mesh.updateWorldMatrix(true, false);
          const geometry = mesh.geometry.clone();
          geometry.applyMatrix4(mesh.matrixWorld);
          // Strip attributes that some primitive geometries do not share.
          for (const name of Object.keys(geometry.attributes)) {
            if (!['position', 'normal', 'uv'].includes(name)) geometry.deleteAttribute(name);
          }
          if (!geometry.getAttribute('uv')) {
            const count = geometry.getAttribute('position').count;
            geometry.setAttribute('uv', new T.BufferAttribute(new Float32Array(count * 2), 2));
          }
          geometries.push(geometry);
        }
        if (typeof mergeGeometries === 'function') {
          merged = mergeGeometries(geometries, false);
        }
        if (merged) {
          const mesh = new T.Mesh(merged, bucket.material);
          mesh.name = 'merged:' + (bucket.meshes[0].name || bucket.material.name || 'static');
          mesh.castShadow = bucket.castShadow;
          mesh.receiveShadow = bucket.receiveShadow;
          mesh.matrixAutoUpdate = false;
          group.add(mesh);
          for (const old of bucket.meshes) removals.push(old);
        }
      } catch (err) {
        console.warn('Static merge skipped for', bucket.material?.name || 'material', err);
      } finally {
        // Always release cloned geometries; merged geometry owns its attributes.
        for (const geometry of geometries) geometry.dispose();
      }
    }
    for (const mesh of removals) {
      mesh.parent?.remove(mesh);
      mesh.geometry?.dispose?.();
    }
  }
  // Static box batching above already collapses the vast majority of repeated voxels.
  // Avoid a CPU-side merge pass here: it costs startup time and can interfere with
  // outline/visibility semantics for nested groups.

  // Helpers for editor controls.
  function setNight(n) {
    const night = Math.max(0, Math.min(1, (n || 0)));
    animated._night = night;
    for (const item of animated.glowSprites) {
      if (item.light?.isSprite) {
        if (!item.light.userData.ownMaterial) {
          item.light.material = materials.glow.clone();
          item.light.userData.ownMaterial = true;
        }
        item.light.material.opacity = Math.min(0.98, (item.base || 1) * (0.035 + night * 0.68));
      } else if (item.light?.isLight) {
        item.light.intensity = (item.base || 1) * (0.08 + night * 1.6);
      }
    }
    materials.glow.opacity = 0.16 + night * 0.75;
    for (const m of animated.localMaterials) m.needsUpdate = true;
    materials.glow.needsUpdate = true;
    materials.goldBright.emissiveIntensity = 0.05 + night * 0.6;
    materials.goldBright.needsUpdate = true;
    materials.water.color.set(night > 0.6 ? 0x3e6d88 : 0x63b9c2);
  }
  function setWeather(name = 'clear') {
    const cloudy = name === 'cloud' || name === 'cloud-sea' || name === 'rain' || name === 'mist' || name === 'sunset';
    cloudMat.opacity = cloudy ? 0.38 : 0.2;
    cloudMat.needsUpdate = true;
    materials.water.opacity = name === 'rain' || name === 'mist' ? 0.82 : 0.7;
    materials.water.needsUpdate = true;
    for (const m of [materials.grass, materials.grassLight]) {
      m.roughness = name === 'rain' ? 0.58 : 0.92;
    }
  }

  animated.update = (t, dt, params = {}) => {
    const wind = params.wind ?? 0.45;
    const cloudSpeed = params.cloudSpeed ?? 0.16;
    const waterfall = params.waterfall ?? 0.8;
    // cloud drift
    for (const c of cloudGroups) {
      c.obj.position.x = c.base.x + Math.sin(t * cloudSpeed * 0.18 + c.phase) * 1.1;
      c.obj.position.z = c.base.z + Math.cos(t * cloudSpeed * 0.14 + c.phase) * 0.7;
    }
    // satellite bob
    for (const f of animated.floaters) {
      f.obj.position.y = f.baseY + Math.sin(t * 0.35 + f.phase) * f.amp;
      f.obj.rotation.y += dt * 0.012 * (f.phase > 4 ? -1 : 1);
    }
    // trees sway via subtle group rotation
    for (let i = 0; i < treeGroups.length; i++) {
      treeGroups[i].rotation.z = Math.sin(t * (0.45 + wind * 0.35) + i * 1.2) * (0.006 + wind * 0.013);
    }
    // pagoda lights flicker
    for (let i = 0; i < animated.glowSprites.length; i++) {
      const g = animated.glowSprites[i];
      if (g.light?.isSprite) {
        const night = animated._night ?? 0;
        g.light.material.opacity = Math.max(0.025, Math.min(0.98, g.base)) * (0.04 + night * 0.72 + Math.sin(t * 4.1 + i * 2.7) * 0.02);
      }
      else if (g.light?.isLight) g.light.intensity = g.base * (0.9 + Math.sin(t * 4.1 + i * 2.7) * 0.08);
    }
    // dragon path: sweeping CatmullRom loop with sine body undulation
    const dragonCurve = animated.dragonCurve || (animated.dragonCurve = new T.CatmullRomCurve3([
      new T.Vector3(-9, 10.5, -6), new T.Vector3(-5, 13.4, 8),
      new T.Vector3(8, 12.1, 9), new T.Vector3(12, 9.0, -2),
      new T.Vector3(3, 8.0, -11), new T.Vector3(-7, 9.0, -8),
    ], true, 'catmullrom', 0.22));
    const dT = (t * 0.032) % 1;
    const dPos = dragonCurve.getPointAt(dT);
    const dTan = dragonCurve.getTangentAt(dT);
    dragonPivot.position.copy(dPos);
    dragonPivot.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), dTan);
    for (let i = 0; i < dragonSegments.length; i++) {
      const f = i / (dragonSegments.length - 1);
      const s = dragonSegments[i];
      const wave = Math.sin(t * 2.2 - f * 8.5) * (0.12 + f * 0.12);
      const side = Math.cos(t * 1.4 - f * 5.0) * (0.04 + f * 0.05);
      s.position.set(side, wave, -f * 5.4);
      s.rotation.z = wave * 0.4;
      s.rotation.y = Math.cos(t * 2.2 - f * 8.5) * 0.08;
    }
    // phoenix path
    const pT = (t * 0.045 + 0.35) % 1;
    const phoenixCurve = animated.phoenixCurve || (animated.phoenixCurve = new T.CatmullRomCurve3([
      new T.Vector3(12, 17, 8), new T.Vector3(-10, 19, 2),
      new T.Vector3(-14, 14.5, -9), new T.Vector3(4, 16.8, -13),
      new T.Vector3(15, 20, 2),
    ], true, 'catmullrom', 0.3));
    const p = phoenixCurve.getPointAt(pT);
    const tan = phoenixCurve.getTangentAt(pT);
    phoenixPivot.position.copy(p);
    phoenixPivot.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), tan);
    phoenixPivot.rotateZ(Math.sin(t * 1.1) * 0.16);
    const flap = Math.sin(t * 4.3) * 0.55;
    for (const w of wings) {
      w.upper.rotation.z = w.side * (0.2 + flap);
      w.lower.rotation.z = w.side * (0.1 + flap * 0.7);
      w.upper.rotation.y = w.side * Math.sin(t * 4.3 + 0.4) * 0.08;
    }
    for (let i = 0; i < tail.length; i++) tail[i].rotation.z = Math.sin(t * 2.4 - i * 0.42) * 0.15;
    // cranes
    for (let i = 0; i < craneBirds.length; i++) {
      const c = craneBirds[i];
      c.obj.position.y = c.baseY + Math.sin(t * 0.65 + c.phase) * 0.5;
      c.wl.rotation.z = Math.sin(t * 3.5 + c.phase) * 0.5;
      c.wr.rotation.z = -Math.sin(t * 3.5 + c.phase) * 0.5;
    }
    // petals
    const pp = animated.petals.geo.attributes.position.array;
    for (let i = 0; i < animated.petals.seeds.length; i++) {
      const s = animated.petals.seeds[i];
      pp[i * 3] = s.x + Math.sin(t * (0.18 + wind * 0.2) + s.phase) * (1.0 + wind * 1.3);
      pp[i * 3 + 1] = 1.0 + ((s.y - t * s.speed * (0.35 + wind * 0.8)) % 18 + 18) % 18;
      pp[i * 3 + 2] = s.z + Math.cos(t * 0.3 + s.phase) * 1.1;
    }
    animated.petals.geo.attributes.position.needsUpdate = true;
    // fireflies
    const fp = animated.fireflies.geo.attributes.position.array;
    for (let i = 0; i < animated.fireflies.seeds.length; i++) {
      const s = animated.fireflies.seeds[i];
      fp[i * 3] = s.p[0] + Math.sin(t * s.speed + s.phase) * 0.9;
      fp[i * 3 + 1] = s.p[1] + Math.cos(t * s.speed * 0.8 + s.phase) * 0.6;
      fp[i * 3 + 2] = s.p[2] + Math.sin(t * s.speed * 0.7 + s.phase * 1.3) * 0.8;
    }
    animated.fireflies.geo.attributes.position.needsUpdate = true;
    // waterfall droplets
    for (const w of animated.waterfallMists) {
      const mesh = w.dropMesh;
      if (!mesh) continue;
      for (let i = 0; i < w.drops.length; i++) {
        const d = w.drops[i];
        d.position.y -= dt * (0.8 + d.userData.speed * 1.6) * waterfall;
        if (d.position.y < d.userData.floor) d.position.y = 0.75;
        d.position.x = d.userData.baseX + Math.sin(t * 2 + d.userData.seed * 9) * 0.04 * waterfall;
        d.updateMatrix();
        mesh.setMatrixAt(i, d.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
  };

  animated.setNight = setNight;
  animated.setWeather = setWeather;
  animated.setWaterfallFlow = (v) => { animated._waterfallFlow = v; };
  animated._waterfallFlow = 1;

  return { root, groups, targets, animated, materials, textures };
}
