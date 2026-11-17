// player.js — first/third-person controller with step climbing, ground detection, jump
import * as THREE from 'three';

export class Player {
  constructor(camera, dom, bounds, audio){
    this.camera = camera;
    this.dom = dom;
    this.audio = audio;
    this.pos = new THREE.Vector3(0, 1.7, 6);
    this.vel = new THREE.Vector3();
    this.yaw = 0;           // yaw=0 faces -Z
    this.pitch = 0;
    this.onGround = true;
    this.height = 1.7;      // eye height (m)
    this.radius = 0.35;
    this.speedWalk = 3.4;
    this.speedRun = 7.0;
    this.jumpV = 6.2;
    this.gravity = -20;
    this.maxStep = 0.55;    // auto-climb steps/curbs up to this height
    this.keys = {};
    this.sensitivity = 0.0022;
    this.enabled = false;
    this.bob = 0;
    this.stepAcc = 0;

    // ground sampling
    this.groundMeshes = [];
    this._ray = new THREE.Raycaster();
    this._down = new THREE.Vector3(0,-1,0);
    this._rayOrigin = new THREE.Vector3();
    this._rayFar = 6;

    // horizontal bounds (inner courtyard limit)
    this.bounds = bounds ? bounds.clone() : null;
    if (this.bounds){
      this.bounds.min.x += 1.0; this.bounds.max.x -= 1.0;
      this.bounds.min.z += 1.0; this.bounds.max.z -= 1.0;
    }
    this.floorY = 0;

    // view mode: 'first' | 'third'
    this.viewMode = 'first';
    this.thirdDist = 4.2;
    this._tmpV = new THREE.Vector3();
    this._tmpV2 = new THREE.Vector3();
    this._camTarget = new THREE.Vector3();
    this._smoothPos = new THREE.Vector3().copy(this.pos);

    this._bind();
    this._sync();
  }
  setGroundMeshes(meshes){
    this.groundMeshes = meshes;
    this._buildMeshes = meshes;
    meshes.forEach(m=>{ m.updateMatrixWorld(true); });
  }
  toggleView(){
    this.viewMode = this.viewMode === 'first' ? 'third' : 'first';
    return this.viewMode;
  }
  _bind(){
    this._onKeyDown = (e)=>{
      if (!this.enabled) return;
      this.keys[e.code] = true;
      if (e.code === 'Space'){ e.preventDefault(); this._tryJump(); }
      if (e.code === 'KeyV' && !e.repeat){ /* V reserved for ultimate in actions */ }
    };
    this._onKeyUp = (e)=>{ this.keys[e.code] = false; };
    this._onMouseMove = (e)=>{
      if (document.pointerLockElement !== this.dom) return;
      this.yaw   -= e.movementX * this.sensitivity;
      this.pitch -= e.movementY * this.sensitivity;
      const lim = Math.PI/2 - 0.05;
      this.pitch = Math.max(-lim, Math.min(lim, this.pitch));
    };
    window.addEventListener('keydown', this._onKeyDown);
    window.addEventListener('keyup', this._onKeyUp);
    document.addEventListener('mousemove', this._onMouseMove);
  }
  setEnabled(v){ this.enabled = v; if (!v) this.keys = {}; }
  _tryJump(){
    if (this.onGround){ this.vel.y = this.jumpV; this.onGround = false; this.audio && this.audio.whoosh(); }
  }
  // Sample the ground height (world Y) under a world XZ point.
  // refFeetY: current foot height; we only accept a surface within [refFeetY-maxStep-0.3, refFeetY+maxStep]
  // so that tall pillars/walls/railings (whose tops are far above) are ignored and don't block walking.
  _groundAt(x, z, refFeetY){
    if (refFeetY == null) refFeetY = this.pos.y - this.height;
    this._rayOrigin.set(x, refFeetY + this.maxStep + 0.4, z);
    this._ray.set(this._rayOrigin, this._down);
    this._ray.far = this.maxStep + 0.8;   // only look within step reach below the ray origin
    let groundY = null;
    if (this.groundMeshes && this.groundMeshes.length){
      const hits = this._ray.intersectObjects(this.groundMeshes, false);
      for (const h of hits){
        const ny = h.face ? h.face.normal.y : 1;
        if (ny < -0.5) continue;             // skip ceilings / undersides
        if (Math.abs(ny) < 0.25) continue;    // skip near-vertical walls
        // accept only surfaces within step range of current feet
        if (h.point.y <= refFeetY + this.maxStep && h.point.y >= refFeetY - 1.2){
          groundY = h.point.y; break;
        }
      }
    }
    // fallback: nearest sane floor — if nothing within reach, assume flat base floor at feet level
    if (groundY == null){
      groundY = (refFeetY > 0.05) ? refFeetY : this.floorY;
    }
    return groundY;
  }
  update(dt){
    if (!this.enabled){ this._sync(); return; }
    const k = this.keys;
    let fwd = 0, strafe = 0;
    if (k['KeyW'] || k['ArrowUp']) fwd += 1;
    if (k['KeyS'] || k['ArrowDown']) fwd -= 1;
    if (k['KeyD'] || k['ArrowRight']) strafe += 1;
    if (k['KeyA'] || k['ArrowLeft']) strafe -= 1;
    const running = (k['ShiftLeft']||k['ShiftRight']);
    const sp = running ? this.speedRun : this.speedWalk;

    const sin = Math.sin(this.yaw), cos = Math.cos(this.yaw);
    let dx = (-sin)*fwd + (cos)*strafe;
    let dz = (-cos)*fwd + (-sin)*strafe;
    const len = Math.hypot(dx,dz);
    if (len > 0){ dx/=len; dz/=len; }

    const targetX = dx*sp, targetZ = dz*sp;
    this.vel.x += (targetX - this.vel.x) * Math.min(1, dt*12);
    this.vel.z += (targetZ - this.vel.z) * Math.min(1, dt*12);

    // --- horizontal move + step climbing ---
    let nx = this.pos.x + this.vel.x * dt;
    let nz = this.pos.z + this.vel.z * dt;

    // bounds clamp
    if (this.bounds){
      nx = Math.max(this.bounds.min.x, Math.min(this.bounds.max.x, nx));
      nz = Math.max(this.bounds.min.z, Math.min(this.bounds.max.z, nz));
    }

    // feet reference height before moving
    const feetY = this.pos.y - this.height;
    const nextGroundY = this._groundAt(nx, nz, feetY);

    // Step up onto surfaces within reach while grounded (stairs / curbs / low platforms)
    if (this.onGround && nextGroundY != null){
      const rise = nextGroundY - feetY;
      if (rise > 0 && rise <= this.maxStep){
        this.pos.y = nextGroundY + this.height;
        this.vel.y = 0;
      }
      // Note: we no longer hard-block on tall hits, because _groundAt already ignores
      // surfaces far above the feet (pillars/walls). The player simply walks on the real floor.
    }
    this.pos.x = nx; this.pos.z = nz;

    // --- vertical (gravity + landing) ---
    this.vel.y += this.gravity * dt;
    this.pos.y += this.vel.y * dt;

    const gY = this._groundAt(this.pos.x, this.pos.z, this.pos.y - this.height);
    if (gY != null && this.pos.y - this.height <= gY + 0.02 && this.vel.y <= 0){
      this.pos.y = gY + this.height; this.vel.y = 0; this.onGround = true;
    } else if (this.pos.y - this.height > gY + 0.03){
      this.onGround = false;
    }
    // hard floor safety
    if (this.pos.y < this.height){ this.pos.y = this.height; this.vel.y = 0; this.onGround = true; }

    // headbob + footsteps
    const moving = Math.hypot(this.vel.x, this.vel.z) > 0.4;
    if (moving && this.onGround){
      this.bob += dt * (running?13:9);
      this.stepAcc += dt * (running?13:9);
      if (this.stepAcc > Math.PI){ this.stepAcc -= Math.PI; this.audio && this.audio.footstep(running); }
    }
    this._sync(moving, running);
  }
  _sync(moving=false, running=false){
    // smooth follow for third-person
    if (this.viewMode === 'first'){
      const bobY = moving && this.onGround ? Math.sin(this.bob)*0.045 : 0;
      const bobX = moving && this.onGround ? Math.cos(this.bob*0.5)*0.03 : 0;
      this.camera.position.set(this.pos.x + bobX, this.pos.y + bobY, this.pos.z);
      const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(this.pitch, this.yaw, 0, 'YXZ'));
      this.camera.quaternion.copy(q);
    } else {
      // third-person: camera orbits behind the player based on yaw/pitch
      const headY = this.pos.y + 0.25;
      const dist = this.thirdDist;
      const cp = Math.cos(this.pitch), sp2 = Math.sin(this.pitch);
      // behind direction (opposite of look) in XZ from yaw
      const back = new THREE.Vector3(Math.sin(this.yaw), 0, Math.cos(this.yaw));
      const desired = new THREE.Vector3(
        this.pos.x + back.x * dist * cp,
        headY - sp2 * dist + 0.6,
        this.pos.z + back.z * dist * cp
      );
      // keep camera above ground a bit
      const cg = this._groundAt(desired.x, desired.z, this.pos.y - this.height);
      if (cg != null && desired.y < cg + 0.4) desired.y = cg + 0.4;
      // smooth
      const k = 1 - Math.pow(0.001, (1/60)); // frame-independent-ish
      this.camera.position.lerp(desired, 0.35);
      const lookAt = new THREE.Vector3(this.pos.x, headY, this.pos.z);
      this.camera.lookAt(lookAt);
    }
  }
  teleport(x,z){ this.pos.x=x; this.pos.z=z; this.vel.set(0,0,0); this._sync(); }
  dispose(){
    window.removeEventListener('keydown', this._onKeyDown);
    window.removeEventListener('keyup', this._onKeyUp);
    document.removeEventListener('mousemove', this._onMouseMove);
  }
}
