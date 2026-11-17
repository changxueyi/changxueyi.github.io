// actions.js — meditation, incense, worship, chanting, sweeping, combat, ultimates
import * as THREE from 'three';

export const ACTIONS = {
  sweep:   { key:'KeyQ', cd:1.2,  dur:1.6 },
  incense: { key:'KeyF', cd:3.0,  dur:1.2 },
  meditate:{ key:'Digit1',cd:1.0, dur:0 },
  chant:   { key:'Digit2',cd:1.0, dur:0 },
  worship: { key:'KeyR', cd:2.0,  dur:1.4 },
  punch:   { key:'Mouse0',cd:0.45,dur:0.45 },
  ultimate:{ key:'KeyV', cd:12.0, dur:1.2 },
  shield:  { key:'KeyC', cd:10.0, dur:4.0 },
};

export class ActionSystem {
  constructor({ scene, camera, player, audio, fx, world, hud, onEvent }){
    Object.assign(this,{scene,camera,player,audio,fx,world,hud,onEvent});
    this.cooldowns = {};
    this.mode = null;          // 'meditate' | 'chant' | null
    this.modeTime = 0;
    this.anim = { name:null, t:0, dur:0 };
    this.shieldT = 0;
    this.punchSide = 1;
    this.viewModel = null;
    this._buildViewModel();
    this._bind();
    // practice counters
    this.stats = { sweep:0, incense:0, meditate:0, chant:0, worship:0 };
    this.targets = { sweep:3, incense:3, meditate:30, chant:20, worship:3 };
    this.merit = 0;
  }
  // A simple first-person "arms/staff" view model for punch/guard feedback
  _buildViewModel(){
    const g = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({color:0x6a4a2a, roughness:0.8, metalness:0.0});
    const staff = new THREE.Mesh(new THREE.CylinderGeometry(0.03,0.035,1.4,10), mat);
    staff.position.set(0.32,-0.34,-0.6); staff.rotation.set(0.2,0,-0.5);
    staff.name='staff'; g.add(staff);
    const fistMat = new THREE.MeshStandardMaterial({color:0xd8a878, roughness:0.9});
    const fist = new THREE.Mesh(new THREE.SphereGeometry(0.09,12,12), fistMat);
    fist.position.set(-0.3,-0.3,-0.55); fist.name='fist'; g.add(fist);
    g.visible=false;
    this.camera.add(g);
    this.scene.add(this.camera);
    this.viewModel = g;
  }
  _bind(){
    this._kd = (e)=>{
      if (!this.hud.isPlaying()) return;
      if (e.repeat) return;
      for (const [name,a] of Object.entries(ACTIONS)){
        if (e.code===a.key){ this.trigger(name); e.preventDefault(); }
      }
      // Left click = punch (only when pointer locked and not clicking UI)
      if (e.code==='Space'){ /* jump handled by player */ }
    };
    this._md = (e)=>{
      if (!this.hud.isPlaying()) return;
      if (e.button===0 && this._locked()){ this.trigger('punch'); }
    };
    window.addEventListener('keydown', this._kd);
    this._dom = document.body;
    this._dom.addEventListener('mousedown', this._md);
  }
  _locked(){ return document.pointerLockElement!=null; }
  ready(name){ return (this.cooldowns[name]||0) <= 0 && this.anim.t<=0; }

  trigger(name){
    if (!this.ready(name) && ACTIONS[name]) {
      // still allow toggling meditation off by pressing again
    }
    const a = ACTIONS[name]; if(!a) return;
    if ((this.cooldowns[name]||0) > 0) return;
    switch(name){
      case 'sweep': this.doSweep(); break;
      case 'incense': this.doIncense(); break;
      case 'meditate': this.toggleMeditate(); break;
      case 'chant': this.toggleChant(); break;
      case 'worship': this.doWorship(); break;
      case 'punch': this.doPunch(); break;
      case 'ultimate': this.doUltimate(); break;
      case 'shield': this.doShield(); break;
    }
  }
  _cd(name,sec){ this.cooldowns[name]=sec; this.hud?.setCooldown(name,sec); }

  setAnim(name,dur){ this.anim.name=name; this.anim.t=dur; this.anim.dur=dur; }

  // ----修行 actions----
  doSweep(){
    this.audio?.sweep();
    this.setAnim('sweep', ACTIONS.sweep.dur);
    this._cd('sweep', ACTIONS.sweep.cd);
    // dust in front
    const dir=new THREE.Vector3(0,0,-1).applyQuaternion(this.camera.quaternion);
    const p=this.camera.position.clone().add(dir.multiplyScalar(1.2)); p.y=0.1;
    this.fx.dust(p, 22, 0.9);
    this.onEvent?.('sweep');
  }
  doIncense(){
    this.audio?.gong(); this.audio?.incense?.();
    this.setAnim('incense', ACTIONS.incense.dur);
    this._cd('incense', ACTIONS.incense.cd);
    // place smoke at an incense burner in front, or in front of player
    const dir=new THREE.Vector3(0,0,-1).applyQuaternion(this.camera.quaternion);
    const p=this.player.pos.clone().add(dir.multiplyScalar(1.6)); p.y=0.9;
    this.fx.incense(p);
    this.onEvent?.('incense');
  }
  doWorship(){
    this.audio?.bell();
    this.setAnim('worship', ACTIONS.worship.dur);
    this._cd('worship', ACTIONS.worship.cd);
    const p=this.player.pos.clone();
    this.fx.auraRing(p, 0.8, 0xf0c860);
    this.onEvent?.('worship');
  }
  toggleMeditate(){
    if (this.mode==='meditate'){ this.endMode(); return; }
    this.mode='meditate'; this.modeTime=0;
    this.audio?.bell();
    this.hud?.subtitle('闭目盘膝，五蕴皆空…');
    this.onEvent?.('meditateStart');
    const p=this.player.pos.clone();
    this.fx.auraRing(p, 0.9, 0xf0c860);
  }
  toggleChant(){
    if (this.mode==='chant'){ this.endMode(); return; }
    this.mode='chant'; this.modeTime=0;
    this.audio?.chant();
    this.hud?.subtitle('南无阿弥陀佛……');
    this.onEvent?.('chantStart');
  }
  endMode(){
    if(this.mode){ this.hud?.subtitle(''); }
    this.mode=null; this.modeTime=0;
    if(this.player){ this.player.speedWalk=3.2; this.player.speedRun=6.4; }
  }

  // ----combat----
  doPunch(){
    this.setAnim('punch', ACTIONS.punch.dur);
    this._cd('punch', ACTIONS.punch.cd);
    this.punchSide *= -1;
    this.audio?.punch();
    // animate view model
    const fist=this.viewModel.getObjectByName('fist');
    const staff=this.viewModel.getObjectByName('staff');
    this.viewModel.visible=true;
    if (fist){ fist.position.x = 0.3*this.punchSide; }
    // hit check: nearest target within range in front -> apply damage
    const enemy=this._meleeEnemy(2.6, 0.5);
    if (enemy){
      enemy.damage(34);
      this.audio?.hit();
      this.fx.hitSpark(enemy.pos.clone().setY(1.2));
      this.hud?.flashHit();
      this.onEvent?.('punch', enemy.pos);
    } else {
      this.onEvent?.('punch', null);
    }
  }
  _meleeEnemy(range, cone){
    const fwd=new THREE.Vector3(0,0,-1).applyQuaternion(this.camera.quaternion); fwd.y=0; fwd.normalize();
    let best=null,bd=1e9;
    for(const t of (this.targets_list||[])){
      if(!t.alive) continue;
      const to=t.pos.clone().sub(this.player.pos); const d=to.length();
      if(d>range) continue; to.y=0; to.normalize();
      if(to.dot(fwd) < cone) continue;
      if(d<bd){bd=d;best=t;}
    }
    return best;
  }
  doUltimate(){
    if ((this.cooldowns['ultimate']||0) > 0) return;
    this.setAnim('ultimate', ACTIONS.ultimate.dur);
    this._cd('ultimate', ACTIONS.ultimate.cd);
    this.audio?.ult();
    this.hud?.flash();
    this.fx.shockwave(this.player.pos.clone(), 7, 0xffb060);
    this.fx.auraRing(this.player.pos.clone(), 1.4, 0xffd890);
    // damage all NON-boss targets in radius (boss must be defeated by melee)
    for(const t of (this.targets_list||[])){
      if(!t.alive) continue;
      if(t.type==='demon') continue;
      if(t.pos.distanceTo(this.player.pos) < 8){ t.damage(200); }
    }
    this.onEvent?.('ultimate');
    this.hud?.subtitle('金刚怒目，降妖伏魔！');
  }
  doShield(){
    if ((this.cooldowns['shield']||0) > 0) return;
    this._cd('shield', ACTIONS.shield.cd);
    this.shieldT = ACTIONS.shield.dur;
    this.audio?.shield();
    this.fx.auraRing(this.player.pos.clone(), 1.0, 0x8fd0ff);
    this.hud?.subtitle('金钟罩 · 万邪不侵');
    this.onEvent?.('shield');
  }

  update(dt){
    // cooldowns
    for(const k in this.cooldowns){ if(this.cooldowns[k]>0){ this.cooldowns[k]-=dt; if(this.cooldowns[k]<=0){ this.hud?.setCooldown(k,0);} else this.hud?.setCooldown(k,this.cooldowns[k]); } }
    // anim timer + view model
    if (this.anim.t>0){
      this.anim.t-=dt;
      this._animView(dt);
      if(this.anim.t<=0){ this.viewModel.visible=false; this.anim.name=null; }
    }
    // shield timer
    if (this.shieldT>0){ this.shieldT-=dt; if(this.shieldT<=0) this.hud?.shieldOff?.(); }
    // meditation / chant progress
    if (this.mode==='meditate'){
      this.modeTime+=dt;
      this.player.speedWalk=0.0; this.player.speedRun=0.0;
      // periodic aura
      if(!this._macc||this.modeTime-this._macc>2.0){ this._macc=this.modeTime; this.fx.auraRing(this.player.pos.clone(),0.9,0xf0c860); }
      this.onEvent?.('meditateTick', this.modeTime);
    } else if (this.mode==='chant'){
      this.modeTime+=dt;
      if(!this._cacc||this.modeTime-this._cacc>1.6){ this._cacc=this.modeTime; this.audio?.chant(); this.fx.auraRing(this.player.pos.clone(),0.6,0x9fd0ff); }
      this.onEvent?.('chantTick', this.modeTime);
    } else {
      if(this._macc){this._macc=0;} if(this._cacc){this._cacc=0;}
    }
  }
  _animView(dt){
    const vm=this.viewModel; const f=vm.getObjectByName('fist'); const s=vm.getObjectByName('staff');
    const k = 1 - this.anim.t/this.anim.dur; // 0..1
    const swing = Math.sin(k*Math.PI);
    vm.visible = true;
    switch(this.anim.name){
      case 'punch':
        if(f){ f.position.z=-0.55 - swing*0.5; f.position.y=-0.3 + swing*0.15; }
        if(s){ s.rotation.z=-0.5 + swing*0.3; }
        break;
      case 'ultimate':
        vm.rotation.z = swing*0.6;
        if(s){ s.rotation.x = 0.2 + swing*1.2; s.position.z=-0.6 - swing*0.4; }
        if(f){ f.position.y=-0.3+swing*0.4; }
        break;
      case 'worship':
        vm.rotation.x = swing*0.5; break;
      case 'sweep':
        if(s){ s.rotation.z=-0.5+swing*1.6; s.position.y=-0.34 - swing*0.2; }
        break;
      case 'incense':
        if(f){ f.position.y=-0.3+swing*0.3; f.position.z=-0.55-swing*0.2; }
        break;
      case 'shield':
        vm.rotation.z = 0; break;
      default: break;
    }
    if(this.anim.t<=0){ vm.rotation.set(0,0,0); if(s){s.position.set(0.32,-0.34,-0.6); s.rotation.set(0.2,0,-0.5);} if(f){f.position.set(-0.3,-0.3,-0.55);} }
  }
}
