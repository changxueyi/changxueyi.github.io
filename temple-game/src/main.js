// main.js — bootstrap, renderer, game loop
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

import { AudioSys } from './audio.js';
import { HUD } from './hud.js';
import { buildWorld, buildSky, addLights } from './world.js';
import { Player } from './player.js';
import { FX } from './fx.js';
import { ActionSystem } from './actions.js';
import { EnemyManager } from './enemies.js';

const app = document.getElementById('app');
const hud = new HUD();
const audio = new AudioSys();

// ---- renderer ----
const renderer = new THREE.WebGLRenderer({ antialias:true, powerPreference:'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.18;
app.appendChild(renderer.domElement);
const canvas = renderer.domElement;

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0xcdb18a, 0.006);

const camera = new THREE.PerspectiveCamera(70, window.innerWidth/window.innerHeight, 0.05, 600);

// ---- post-processing (subtle bloom) ----
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 0.35, 0.6, 0.85);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// ---- systems ----
const fx = new FX(scene);
const enemyMgr = new EnemyManager(scene);
let player, actions, world, lights;

const tmpV = new THREE.Vector3();

function boot(){
  buildSky(scene);
  lights = addLights(scene);

  buildWorld(scene, (p,txt)=>hud.setLoading(0.1+p*0.75, txt)).then((w)=>{
    world=w;

    // Determine courtyard center + bounds from temple box
    const box = world.templeBox;
    const center = new THREE.Vector3(); box.getCenter(center);
    const size = new THREE.Vector3(); box.getSize(size);
    const bounds = new THREE.Box3(
      new THREE.Vector3(center.x - size.x*0.42, 0, center.z - size.z*0.42),
      new THREE.Vector3(center.x + size.x*0.42, 0, center.z + size.z*0.42)
    );

    // Place nun NPC standing near center, plus a couple ambient monks
    const nun = world.nun;
    nun.position.set(center.x - 3.0, 0, center.z + 2.0);
    nun.rotation.y = Math.PI; // face +Z toward player
    scene.add(nun);
    // second monk NPC standing opposite
    const monkNpc = world.monkProto.clone(true);
    monkNpc.position.set(center.x + 3.0, 0, center.z + 2.0);
    monkNpc.rotation.y = Math.PI;
    scene.add(monkNpc);
    // a seated meditation monk near an incense burner
    const monkNpc2 = world.monkProto.clone(true);
    monkNpc2.position.set(center.x, 0, center.z + 5.0);
    monkNpc2.rotation.y = 0.0;
    monkNpc2.scale.multiplyScalar(0.98);
    scene.add(monkNpc2);

    // Ground meshes for step climbing / floor detection (temple + pagoda surfaces)
    const groundMeshes = [];
    world.temple.traverse(o=>{ if(o.isMesh) groundMeshes.push(o); });
    world.pagoda.traverse(o=>{ if(o.isMesh) groundMeshes.push(o); });

    // Player starts in the open courtyard, facing the bright open side (toward sky + pagoda)
    player = new Player(camera, canvas, bounds, audio);
    player.setGroundMeshes(groundMeshes);
    player.pos.set(center.x, 1.7, center.z + size.z*0.28);
    player.yaw = 0.0; // yaw=0 faces -Z -> toward bright open courtyard + pagoda
    player._sync();

    // Player avatar (visible in third-person view) — clone of the monk model
    const avatar = world.monkProto.clone(true);
    scene.add(avatar);
    player.avatar = avatar;
    player.avatar.visible = false; // hidden in first-person
    if (world.monkAnimations && world.monkAnimations.length){
      // reuse the same idle animation clip on the avatar
      player.avatarMixer = new THREE.AnimationMixer(avatar);
      player.avatarMixer.clipAction(world.monkAnimations[0]).play();
    }

    hud.setLoading(0.9, '燃香点烛…');

    actions = new ActionSystem({
      scene, camera, player, audio, fx, world, hud,
      onEvent: handleEvent,
    });

    // Wire combat targets
    actions.targets_list = enemyMgr.list;

    // Spawn training dummies near center
    enemyMgr.spawnTraining(new THREE.Vector3(center.x, 0, center.z + 7.0));

    // FX: incense burners with smoke around courtyard
    const burnerPositions = [
      new THREE.Vector3(center.x-4,0,center.z+4),
      new THREE.Vector3(center.x+4,0,center.z+4),
    ];
    for(const bp of burnerPositions){
      // a small burner mesh
      const burner = new THREE.Mesh(new THREE.CylinderGeometry(0.35,0.45,0.5,12),
        new THREE.MeshStandardMaterial({color:0x3a2c1a, metalness:0.6, roughness:0.5}));
      burner.position.copy(bp).setY(0.25); burner.castShadow=true; scene.add(burner);
      fx.incense(bp.clone().setY(0.6));
      // continuous smoke timer
      setInterval(()=>{ if(actions && player && bp.distanceTo(player.pos)<40) fx.incense(bp.clone().setY(0.6)); }, 2600);
    }

    hud.setLoading(1.0, '入寺参禅');
    hud.hideLoader();
    enableStart();
    animate();
  }).catch(err=>{
    console.error(err);
    hud.loadtxt.textContent = '加载失败：' + err.message;
  });
}

// ---- event handling for quests / merit ----
function handleEvent(type, data){
  switch(type){
    case 'sweep':   actions.stats.sweep++;   hud.setQuest('sweep', actions.stats.sweep, actions.targets.sweep); if(actions.stats.sweep>=actions.targets.sweep) hud.addGong(20); break;
    case 'incense': actions.stats.incense++; hud.setQuest('incense', actions.stats.incense, actions.targets.incense); break;
    case 'worship': actions.stats.worship++; hud.setQuest('worship', actions.stats.worship, actions.targets.worship); break;
    case 'meditateTick':
      actions.stats.meditate = data;
      hud.setQuest('meditate', data, actions.targets.meditate);
      hud.setSati(Math.min(100, data/actions.targets.meditate*100));
      hud.setQi(Math.min(100, hud.qi + 0.5));
      break;
    case 'chantTick':
      actions.stats.chant = data;
      hud.setQuest('chant', data, actions.targets.chant);
      hud.setQi(Math.min(100, hud.qi + 0.5));
      break;
    case 'ultimate':
      break;
  }
  // Any quest progress may complete all课业 -> trigger victory check
  checkVictory();
}

function checkVictory(){
  const done = ['sweep','incense','meditate','chant','worship'].every(k=>{
    const cur = actions.stats[k]; const tgt = actions.targets[k];
    return cur>=tgt;
  });
  if(done && !window.__won){
    window.__won = true;
    const center = world.templeBox.getCenter(new THREE.Vector3());
    const dp = new THREE.Vector3(center.x, 0, center.z + 5.0);
    enemyMgr.spawnDemon(dp);
    hud.subtitle('课业圆满！心魔已现 · 以武证道', 4);
    audio.gong();
  }
}

function enableStart(){
  const startEl=document.getElementById('start');
  const btn=document.getElementById('startBtn');
  btn.addEventListener('click', ()=>{
    audio.init();
    audio.loadBGM('./assets/audio/temple_bgm.ogg');
    startEl.style.transition='opacity .6s'; startEl.style.opacity='0';
    setTimeout(()=>startEl.remove(), 700);
    canvas.requestPointerLock?.();
    player.setEnabled(true);
    hud.startPlay();
    window.__started=true;
    audio.ui();
  });
  // click canvas to re-lock
  canvas.addEventListener('click', ()=>{
    if(window.__started && document.pointerLockElement!==canvas) canvas.requestPointerLock?.();
  });
}

// ---- input for actions ----
function trigger(name){
  if (name === 'view'){
    if (!player) return;
    const mode = player.toggleView();
    hud.subtitle(mode==='third' ? '第三人称视角 · 可见己身' : '第一人称视角', 1.6);
    hud.setViewLabel?.(mode);
    return;
  }
  actions?.trigger(name);
}

// View toggle: Tab switches first-person <-> third-person (see player)
window.addEventListener('keydown', (e)=>{
  if (!hud.isPlaying()) return;
  if (e.code === 'Tab'){
    e.preventDefault();
    const mode = player.toggleView();
    hud.subtitle(mode==='third' ? '第三人称视角 · 可见己身' : '第一人称视角', 1.6);
    hud.setViewLabel?.(mode);
  }
});
window.__game = { trigger,
  get actions(){return actions;}, get player(){return player;},
  get world(){return world;}, get scene(){return scene;}, get renderer(){return renderer;}, get camera(){return camera;} };

// pause on Esc (pointer unlock) — do NOT auto pause, just release; resume on click.
document.addEventListener('pointerlockchange', ()=>{
  if(!document.pointerLockElement && window.__started && !window.__wonPause){
    // released pointer; show pause overlay
    // showOverlay('暂 停','点击「继续」返回修行');
  }
});

// ---- resize ----
window.addEventListener('resize', ()=>{
  camera.aspect = window.innerWidth/window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
});

// ---- main loop ----
let last=performance.now();
let fpsAcc=0, fpsCnt=0, fpsTimer=0;
const fpsEl=document.getElementById('fps');

function animate(){
  requestAnimationFrame(animate);
  const now=performance.now();
    let dt=(now-last)/1000; last=now;
  if(dt>0.05) dt=0.05; // clamp

  const playing = hud.isPlaying();

  if(playing){
    player.update(dt);
    // third-person avatar follows player
    if (player.avatar){
      const showAvatar = player.viewMode === 'third';
      player.avatar.visible = showAvatar;
      if (showAvatar){
        player.avatar.position.set(player.pos.x, player.pos.y - player.height, player.pos.z);
        player.avatar.rotation.y = player.yaw + Math.PI; // model faces its own forward
        if (player.avatarMixer) player.avatarMixer.update(dt);
      }
    }
    actions.update(dt);
    enemyMgr.update(dt, player.pos);
    fx.update(dt);
    hud.update(dt);
    // shield visual state
    if(actions.shieldT>0){ hud.setUltReady?.(false); }
    // ultimate ready indicator
    const ultCd = actions.cooldowns['ultimate']||0;
    hud.setUltReady(ultCd<=0 && playing);
    // ambient qi regen
    hud.setQi(Math.min(100, hud.qi + dt*0.6));
    // demon attacks player when close
    for(const e of enemyMgr.list){
      if(e.alive && e.type==='demon'){
        const d=e.pos.distanceTo(player.pos);
        if(d<1.8 && (actions.shieldT||0)<=0){
          if(!e._atkCd || e._atkCd<=0){ e._atkCd=1.2; hud.setHp(hud.hp-6); hud.damageFlash(); audio.hit(); }
        }
      }
      if(e._atkCd>0) e._atkCd-=dt;
      if(!e.alive && !window.__win){ /* handled below */ }
    }
    checkWin();
  }

  composer.render();

  // fps
  fpsCnt++; fpsTimer+=dt;
  if(fpsTimer>=0.5){ fpsEl.textContent = Math.round(fpsCnt/fpsTimer)+' fps'; fpsCnt=0; fpsTimer=0; }
}

function checkWin(){
  if(window.__won && !window.__win){
    // all dummies dead and demon dead => victory
    const anyDemon = enemyMgr.list.some(e=>e.type==='demon'&&e.alive);
    if(!anyDemon){
      window.__win=true;
      player.setEnabled(false);
      if(document.pointerLockElement) document.exitPointerLock();
      showOverlay('道 成','你已扫尽尘埃、敬香礼佛、入定诵经，并以「伏魔」之力降服心魔。<br/>功德圆满 · 共修 ' + Math.round(hud.gong) + ' 点', '重 新 修 行', ()=>location.reload());
      audio.bell();
    }
  }
}

function showOverlay(title, text, btnText, cb){
  const ov=document.getElementById('overlay');
  document.getElementById('ovTitle').textContent=title;
  document.getElementById('ovText').innerHTML=text;
  const b=document.getElementById('ovBtn'); b.textContent=btnText;
  b.onclick=()=>{ ov.classList.remove('show'); cb&&cb(); };
  ov.classList.add('show');
}

// Kick off
boot();
