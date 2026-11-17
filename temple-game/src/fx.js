// fx.js — visual effects: incense smoke, dust, prayer glow, hit sparks, shockwave
import * as THREE from 'three';

// Soft round sprite texture (canvas)
function makeSprite(inner='rgba(255,255,255,1)', outer='rgba(255,255,255,0)'){
  const c=document.createElement('canvas'); c.width=c.height=64;
  const g=c.getContext('2d');
  const grd=g.createRadialGradient(32,32,0,32,32,32);
  grd.addColorStop(0,inner); grd.addColorStop(1,outer);
  g.fillStyle=grd; g.fillRect(0,0,64,64);
  const tex=new THREE.CanvasTexture(c); tex.colorSpace=THREE.SRGBColorSpace; return tex;
}

export class FX {
  constructor(scene){
    this.scene=scene;
    this.items=[]; // {obj, life, max, update}
    this._spriteTex = makeSprite();
    this._smokeTex = makeSprite('rgba(220,215,205,0.9)','rgba(220,215,205,0)');
  }
  _add(obj, life, update){
    this.scene.add(obj);
    this.items.push({obj, life, max:life, update});
    return obj;
  }
  // Incense smoke column at a point
  incense(pos, color=0xaab0c0){
    const g = new THREE.BufferGeometry();
    const N=26; const arr=new Float32Array(N*3); const seed=[];
    for(let i=0;i<N;i++){ arr[i*3]=pos.x; arr[i*3+1]=pos.y; arr[i*3+2]=pos.z; seed.push(Math.random()*Math.PI*2); }
    g.setAttribute('position', new THREE.BufferAttribute(arr,3));
    const mat=new THREE.PointsMaterial({
      size:0.5, map:this._smokeTex, transparent:true, depthWrite:false,
      color, opacity:0.5, blending:THREE.NormalBlending, sizeAttenuation:true
    });
    const pts=new THREE.Points(g,mat);
    const life=8, max=8;
    let t=0;
    this._add(pts, life, (o,dt)=>{
      t+=dt;
      const p=o.geometry.attributes.position;
      for(let i=0;i<N;i++){
        p.array[i*3+1]+=dt*(0.5+ (i%5)*0.05);
        p.array[i*3]  +=Math.sin(t*1.2+seed[i])*dt*0.12;
        p.array[i*3+2]+=Math.cos(t*1.0+seed[i])*dt*0.12;
      }
      p.needsUpdate=true;
      mat.opacity = 0.5*(1 - t/max);
      mat.size = 0.4 + t*0.08;
    });
  }
  // Dust puff (sweep / footstep)
  dust(pos, n=18, spread=0.6, color=0xcbb89a){
    const g=new THREE.BufferGeometry();
    const arr=new Float32Array(n*3); const vel=[];
    for(let i=0;i<n;i++){
      arr[i*3]=pos.x; arr[i*3+1]=pos.y+0.05; arr[i*3+2]=pos.z;
      vel.push(new THREE.Vector3((Math.random()-0.5)*spread, Math.random()*0.4+0.1,(Math.random()-0.5)*spread));
    }
    g.setAttribute('position',new THREE.BufferAttribute(arr,3));
    const mat=new THREE.PointsMaterial({size:0.28,map:this._spriteTex,transparent:true,depthWrite:false,color,opacity:0.7});
    const pts=new THREE.Points(g,mat);
    let t=0; const max=1.1;
    this._add(pts,max,(o,dt)=>{
      t+=dt; const p=o.geometry.attributes.position;
      for(let i=0;i<n;i++){ p.array[i*3]+=vel[i].x*dt; p.array[i*3+1]+=vel[i].y*dt; p.array[i*3+2]+=vel[i].z*dt; vel[i].y-=dt*0.6; }
      p.needsUpdate=true; mat.opacity=0.7*(1-t/max); mat.size=0.28+t*0.3;
    });
  }
  // Golden glow ring (meditation aura)
  auraRing(pos, radius=0.9, color=0xf0c860){
    const geo=new THREE.RingGeometry(radius*0.7, radius, 48);
    const mat=new THREE.MeshBasicMaterial({color, transparent:true, opacity:0.0, side:THREE.DoubleSide, depthWrite:false, blending:THREE.AdditiveBlending});
    const ring=new THREE.Mesh(geo,mat);
    ring.rotation.x=-Math.PI/2; ring.position.set(pos.x, 0.03, pos.z);
    let t=0; const max=1.2;
    this._add(ring,max,(o,dt)=>{
      t+=dt; o.scale.setScalar(0.5 + t*1.6); mat.opacity=Math.sin(Math.min(1,t/max)*Math.PI)*0.8;
    });
    // floating particles
    this._sparkle(pos, radius, 22, color);
  }
  _sparkle(pos, radius, n, color){
    const g=new THREE.BufferGeometry();
    const arr=new Float32Array(n*3); const seeds=[];
    for(let i=0;i<n;i++){
      const a=Math.random()*Math.PI*2, r=Math.random()*radius;
      arr[i*3]=pos.x+Math.cos(a)*r; arr[i*3+1]=pos.y+Math.random()*1.4; arr[i*3+2]=pos.z+Math.sin(a)*r;
      seeds.push({a, r, sp:0.3+Math.random()*0.5});
    }
    g.setAttribute('position',new THREE.BufferAttribute(arr,3));
    const mat=new THREE.PointsMaterial({size:0.12,map:this._spriteTex,transparent:true,depthWrite:false,color,blending:THREE.AdditiveBlending,opacity:0.9});
    const pts=new THREE.Points(g,mat);
    let t=0; const max=2.2;
    this._add(pts,max,(o,dt)=>{
      t+=dt; const p=o.geometry.attributes.position;
      for(let i=0;i<n;i++){ p.array[i*3+1]+=dt*seeds[i].sp; p.array[i*3]+=Math.sin(t+seeds[i].a)*dt*0.1; }
      p.needsUpdate=true; mat.opacity=0.9*(1-t/max);
    });
  }
  // Hit spark burst
  hitSpark(pos, color=0xffd27a){
    const n=16; const g=new THREE.BufferGeometry();
    const arr=new Float32Array(n*3); const vel=[];
    for(let i=0;i<n;i++){ arr[i*3]=pos.x;arr[i*3+1]=pos.y;arr[i*3+2]=pos.z;
      vel.push(new THREE.Vector3((Math.random()-0.5)*4,Math.random()*3,(Math.random()-0.5)*4)); }
    g.setAttribute('position',new THREE.BufferAttribute(arr,3));
    const mat=new THREE.PointsMaterial({size:0.18,map:this._spriteTex,transparent:true,depthWrite:false,color,blending:THREE.AdditiveBlending});
    const pts=new THREE.Points(g,mat);
    let t=0; const max=0.5;
    this._add(pts,max,(o,dt)=>{t+=dt;const p=o.geometry.attributes.position;
      for(let i=0;i<n;i++){p.array[i*3]+=vel[i].x*dt;p.array[i*3+1]+=vel[i].y*dt;p.array[i*3+2]+=vel[i].z*dt;vel[i].y-=dt*8;}
      p.needsUpdate=true; mat.opacity=1-t/max;});
  }
  // Shockwave ring (ultimate)
  shockwave(pos, maxR=6, color=0xffb060){
    const geo=new THREE.RingGeometry(0.2,0.5,64);
    const mat=new THREE.MeshBasicMaterial({color,transparent:true,opacity:1,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending});
    const ring=new THREE.Mesh(geo,mat); ring.rotation.x=-Math.PI/2; ring.position.set(pos.x,0.06,pos.z);
    let t=0; const max=0.9;
    this._add(ring,max,(o,dt)=>{t+=dt; const k=t/max; o.scale.setScalar(1+k*maxR*2); mat.opacity=1-k;});
    // dome
    const dome=new THREE.Mesh(new THREE.SphereGeometry(0.5,24,16,0,Math.PI*2,0,Math.PI/2),
      new THREE.MeshBasicMaterial({color,transparent:true,opacity:0.35,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.DoubleSide}));
    dome.position.set(pos.x,0,pos.z);
    this._add(dome,0.7,(o,dt)=>{t+=dt;o.scale.setScalar(1+t*maxR); o.material.opacity=0.35*(1-t/0.7);});
    this.hitSpark(new THREE.Vector3(pos.x,1.2,pos.z), color);
  }
  update(dt){
    for(let i=this.items.length-1;i>=0;i--){
      const it=this.items[i]; it.life-=dt;
      if(it.update) it.update(it.obj, dt);
      if(it.life<=0){ this.scene.remove(it.obj); if(it.obj.geometry)it.obj.geometry.dispose(); if(it.obj.material)it.obj.material.dispose(); this.items.splice(i,1); }
    }
  }
}
