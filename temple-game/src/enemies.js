// enemies.js — simple training dummies / "心魔" opponents for combat
import * as THREE from 'three';

export class Enemy {
  constructor(scene, pos, {hp=100, type='dummy'}={}){
    this.scene=scene; this.pos=pos.clone(); this.hp=hp; this.maxHp=hp; this.alive=true;
    this.type=type;
    this.group=new THREE.Group();
    // body
    const mat=new THREE.MeshStandardMaterial({color: type==='demon'?0x5a1f2a:0x6b5236, roughness:0.8});
    const body=new THREE.Mesh(new THREE.CapsuleGeometry(0.28,0.9,6,12), mat);
    body.position.y=0.95; body.castShadow=true; this.group.add(body); this.body=body;
    // head
    const head=new THREE.Mesh(new THREE.SphereGeometry(0.22,16,16), new THREE.MeshStandardMaterial({color:0xc9a06a,roughness:0.9}));
    head.position.y=1.6; head.castShadow=true; this.group.add(head); this.head=head;
    // "魔" aura color
    if(type==='demon'){
      const ring=new THREE.Mesh(new THREE.RingGeometry(0.5,0.7,24), new THREE.MeshBasicMaterial({color:0xff3030,transparent:true,opacity:0.5,side:THREE.DoubleSide,depthWrite:false}));
      ring.rotation.x=-Math.PI/2; ring.position.y=0.05; this.group.add(ring); this.aura=ring;
    }
    // hp bar sprite
    this.hpCanvas=document.createElement('canvas'); this.hpCanvas.width=128;this.hpCanvas.height=16;
    this.hpTex=new THREE.CanvasTexture(this.hpCanvas);
    this.hpSprite=new THREE.Sprite(new THREE.SpriteMaterial({map:this.hpTex,depthTest:false,transparent:true}));
    this.hpSprite.scale.set(1.0,0.13,1); this.hpSprite.position.y=2.05; this.group.add(this.hpSprite);
    this._drawHp();
    this.group.position.copy(this.pos);
    scene.add(this.group);
    this.spawnT=0;
  }
  _drawHp(){
    const c=this.hpCanvas.getContext('2d');
    c.clearRect(0,0,128,16);
    c.fillStyle='rgba(0,0,0,0.6)'; c.fillRect(0,4,128,8);
    const k=Math.max(0,this.hp/this.maxHp);
    c.fillStyle=this.type==='demon'?'#ff5050':'#ffd27a';
    c.fillRect(0,4,128*k,8);
    this.hpTex.needsUpdate=true;
  }
  damage(d){ if(!this.alive)return; this.hp-=d; this._drawHp();
    // flash
    this.body.material.emissive = new THREE.Color(0xff4422); this.body.material.emissiveIntensity=1;
    setTimeout(()=>{ if(this.body.material) this.body.material.emissiveIntensity=0; },120);
    if(this.hp<=0) this.die();
  }
  die(){
    if(!this.alive) return; this.alive=false;
    // shrink animation handled in update
  }
  update(dt, playerPos){
    if(!this.alive){
      this.group.scale.multiplyScalar(Math.max(0,1-dt*4));
      this.group.position.y -= dt*0.5;
      if(this.group.scale.x<0.05){ this.scene.remove(this.group); }
      return;
    }
    this.spawnT+=dt;
    // spawn grow-in
    const s=Math.min(1,this.spawnT*3);
    this.group.scale.setScalar(s);
    // demon chases player slowly
    if(this.type==='demon' && playerPos){
      const to=playerPos.clone().sub(this.pos); to.y=0; const d=to.length();
      if(d>1.6){ to.normalize(); this.pos.addScaledVector(to, dt*1.4); this.group.position.copy(this.pos); this.group.lookAt(playerPos.x, this.pos.y, playerPos.z); }
    }
    // idle bob
    this.body.position.y = 0.95 + Math.sin(this.spawnT*2)*0.03;
  }
}

export class EnemyManager {
  constructor(scene){ this.scene=scene; this.list=[]; }
  spawnTraining(center){
    // three dummies in courtyard
    this.add(new Enemy(this.scene, center.clone().add(new THREE.Vector3(-2.5,0,-2))));
    this.add(new Enemy(this.scene, center.clone().add(new THREE.Vector3( 0,0,-3.2))));
    this.add(new Enemy(this.scene, center.clone().add(new THREE.Vector3( 2.5,0,-2))));
  }
  spawnDemon(pos){ const e=new Enemy(this.scene,pos,{hp:160,type:'demon'}); this.add(e); return e; }
  add(e){ this.list.push(e); return e; }
  get targets(){ return this.list; }
  update(dt, playerPos){
    for(const e of this.list) e.update(dt, playerPos);
    // cleanup dead-and-shrunk IN PLACE (keep same array reference so combat targeting stays valid)
    for(let i=this.list.length-1;i>=0;i--){
      const e=this.list[i];
      if(!e.alive && e.group.scale.x<0.05){ this.list.splice(i,1); }
    }
  }
}
