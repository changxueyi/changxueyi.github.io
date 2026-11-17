// world.js — loads + optimizes temple/pagoda/NPC models, builds sky/lights/effects
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const _loader = new GLTFLoader();
_loader.setMeshoptDecoder( MeshoptDecoder );

function loadGLB(url){
  return new Promise((res, rej) => _loader.load(url, res, undefined, rej));
}

// Collect a scene's overall bounding box after scaling/orientation.
function normalizeModel(root, targetHeight){
  // Orient Y-up, compute bbox, scale to targetHeight (meters), place feet at y=0, center x/z.
  root.updateMatrixWorld(true);
  let box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3(); box.getSize(size);
  let s = targetHeight / size.y;
  root.scale.multiplyScalar(s);
  root.updateMatrixWorld(true);
  box = new THREE.Box3().setFromObject(root);
  const center = new THREE.Vector3(); box.getCenter(center);
  root.position.x -= center.x;
  root.position.z -= center.z;
  root.position.y -= box.min.y;
  root.updateMatrixWorld(true);
  return { box: new THREE.Box3().setFromObject(root), height: targetHeight };
}

// Traverse, enable shadows, fix materials for crisp look (no blurry reflections).
function polishMaterials(root, {castShadow=true, receiveShadow=true}={}){
  root.traverse(o=>{
    if (!o.isMesh) return;
    o.castShadow = castShadow; o.receiveShadow = receiveShadow;
    o.frustumCulled = true;
    const mats = Array.isArray(o.material)?o.material:[o.material];
    for (const m of mats){
      if (!m) continue;
      if ('map' in m && m.map){
        m.map.anisotropy = 8;
        m.map.minFilter = THREE.LinearMipmapLinearFilter;
        m.map.magFilter = THREE.LinearFilter;
        m.map.generateMipmaps = true;
      }
      if ('roughness' in m && m.roughness > 0.85) m.roughness = 0.85;
      if ('metalness' in m) m.metalness = Math.min(m.metalness, 0.05);
      m.envMapIntensity = 0.6;
      m.needsUpdate = true;
    }
  });
}

export async function buildWorld(scene, onProgress){
  const objs = {};

  onProgress(0.1, '加载古寺…');
  const templeGltf = await loadGLB('./assets/temple_lite.glb');
  const temple = templeGltf.scene;
  // temple authored in cm-ish; normalize to ~26m footprint, keep proportions.
  const tb = normalizeModel(temple, 13.0);
  polishMaterials(temple, {castShadow:true, receiveShadow:true});
  scene.add(temple);
  objs.temple = temple;
  objs.templeBox = tb.box;
  onProgress(0.4, '加载佛塔…');

  const pagodaGltf = await loadGLB('./assets/pagoda_lite.glb');
  const pagoda = pagodaGltf.scene;
  // Place pagoda offset outside courtyard as a distant landmark, taller.
  const pb = normalizeModel(pagoda, 42.0);
  polishMaterials(pagoda, {castShadow:false, receiveShadow:true});
  // Position far behind temple
  const tc = new THREE.Vector3(); tb.box.getCenter(tc);
  pagoda.position.x = tc.x;
  pagoda.position.z = tb.box.min.z - 34;
  scene.add(pagoda);
  objs.pagoda = pagoda;
  onProgress(0.62, '加载僧人…');

  // Monk (rigged, has idle animation). We'll use as player avatar in shadow + NPC.
  const monkGltf = await loadGLB('./assets/monk_lite.glb');
  const monk = monkGltf.scene;
  const mb = normalizeModel(monk, 1.75);
  polishMaterials(monk, {castShadow:true, receiveShadow:true});
  let monkMixer = null;
  if (monkGltf.animations && monkGltf.animations.length){
    monkMixer = new THREE.AnimationMixer(monk);
    monkMixer.clipAction(monkGltf.animations[0]).play();
  }
  objs.monkProto = monk;
  objs.monkMixer = monkMixer;
  objs.monkAnimations = monkGltf.animations;

  onProgress(0.8, '加载同修…');
  const nunGltf = await loadGLB('./assets/nun_lite.glb');
  const nun = nunGltf.scene;
  normalizeModel(nun, 1.68);
  polishMaterials(nun, {castShadow:true, receiveShadow:true});
  objs.nun = nun;

  return objs;
}

// Sky dome with gradient + sun; plus sky color helper.
export function buildSky(scene){
  const geo = new THREE.SphereGeometry(400, 32, 16);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite:false,
    uniforms:{
      top:{value:new THREE.Color(0x4a6a92)},
      mid:{value:new THREE.Color(0xcdb18a)},
      bot:{value:new THREE.Color(0x6a5540)},
      sunDir:{value:new THREE.Vector3(0.4,0.35,-0.7).normalize()},
    },
    vertexShader:`varying vec3 vW; void main(){ vW=normalize(position); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader:`
      varying vec3 vW; uniform vec3 top,mid,bot,sunDir;
      void main(){
        float h = vW.y*0.5+0.5;
        vec3 col = mix(bot, mid, smoothstep(0.0,0.5,h));
        col = mix(col, top, smoothstep(0.45,1.0,h));
        float s = max(dot(normalize(vW), normalize(sunDir)),0.0);
        col += vec3(1.0,0.85,0.6)*pow(s,64.0)*1.4;      // sun disc
        col += vec3(1.0,0.8,0.5)*pow(s,8.0)*0.25;        // glow
        gl_FragColor=vec4(col,1.0);
      }`
  });
  const sky = new THREE.Mesh(geo, mat);
  scene.add(sky);
  return sky;
}

export function addLights(scene){
  const hemi = new THREE.HemisphereLight(0xdce8f5, 0x7a6242, 1.05);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff0d0, 2.6);
  sun.position.set(22, 46, 30);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048,2048);
  sun.shadow.camera.near = 1; sun.shadow.camera.far = 160;
  const d = 34;
  sun.shadow.camera.left=-d; sun.shadow.camera.right=d;
  sun.shadow.camera.top=d; sun.shadow.camera.bottom=-d;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.02;
  scene.add(sun);
  const amb = new THREE.AmbientLight(0x9c8c72, 0.7);
  scene.add(amb);
  return { sun, hemi, amb };
}
