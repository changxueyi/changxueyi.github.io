// hud.js — DOM HUD controller
export class HUD {
  constructor(){
    this.hud=document.getElementById('hud');
    this.bar=document.getElementById('bar');
    this.loadtxt=document.getElementById('loadtxt');
    this.prompt=document.getElementById('prompt');
    this.sub=document.getElementById('subtitle');
    this.vHp=document.getElementById('vHp'); this.vQi=document.getElementById('vQi');
    this.vSati=document.getElementById('vSati'); this.vGong=document.getElementById('vGong');
    this.mHp=document.querySelector('#mHp > i'); this.mQi=document.querySelector('#mQi > i'); this.mSati=document.querySelector('#mSati > i');
    this.q={ sweep:document.getElementById('q_sweep'), incense:document.getElementById('q_incense'),
      meditate:document.getElementById('q_meditate'), chant:document.getElementById('q_chant'), worship:document.getElementById('q_worship') };
    this.qRows={}; document.querySelectorAll('#quest p[data-q]').forEach(p=>this.qRows[p.dataset.q]=p);
    this.flashEl=document.getElementById('flash'); this.dmgEl=document.getElementById('dmg');
    this.cross=document.getElementById('crosshair');
    this.skillEls={}; document.querySelectorAll('.skill').forEach(el=>this.skillEls[el.dataset.act]=el);
    this.subT=0; this._playing=false;
    // stats
    this.hp=100; this.qi=100; this.sati=0; this.gong=0;
    // bind skill bar clicks
    document.querySelectorAll('.skill').forEach(el=>{
      el.addEventListener('click',(e)=>{ e.stopPropagation(); window.__game?.trigger?.(el.dataset.act); });
    });
    this._upd();
  }
  setLoading(p,txt){ if(this.bar)this.bar.style.width=`${Math.round(p*100)}%`; if(txt&&this.loadtxt)this.loadtxt.textContent=txt; }
  hideLoader(){ const l=document.getElementById('loader'); if(l){ l.style.transition='opacity .6s'; l.style.opacity='0'; setTimeout(()=>l.remove(),700);} }
  startPlay(){ this._playing=true; this.hud.classList.add('show'); }
  isPlaying(){ return this._playing; }
  setPlaying(v){ this._playing=v; }
  _upd(){
    this.vHp.textContent=Math.round(this.hp);
    this.vQi.textContent=Math.round(this.qi);
    this.vSati.textContent=Math.round(this.sati);
    this.vGong.textContent=Math.round(this.gong);
    this.mHp.style.width=this.hp+'%';
    this.mQi.style.width=this.qi+'%';
    this.mSati.style.width=Math.min(100,this.sati/100*100)+'%';
  }
  addGong(n){ this.gong+=n; this._upd(); }
  setQi(v){ this.qi=Math.max(0,Math.min(100,v)); this._upd(); }
  setHp(v){ this.hp=Math.max(0,Math.min(100,v)); this._upd(); }
  setSati(v){ this.sati=v; this._upd(); }
  setQuest(k,cur,tgt){
    if(this.q[k]) this.q[k].textContent = k==='meditate'||k==='chant' ? `${Math.min(Math.floor(cur),tgt)}/${tgt}s` : `${Math.min(cur,tgt)}/${tgt}`;
    if(cur>=tgt && this.qRows[k] && !this.qRows[k].classList.contains('done')){
      this.qRows[k].classList.add('done'); this.gong += 50; this._upd();
    }
  }
  promptSet(html){ if(!this.prompt) return; if(html){ this.prompt.innerHTML=html; this.prompt.classList.add('show'); } else this.prompt.classList.remove('show'); }
  subtitle(text, dur=2.4){ this.sub.textContent=text; this.sub.classList.add('show'); this.subT=dur; }
  update(dt){ if(this.subT>0){ this.subT-=dt; if(this.subT<=0) this.sub.classList.remove('show'); } }
  flash(){ const e=this.flashEl; e.style.opacity='1'; setTimeout(()=>e.style.opacity='0',120); }
  flashHit(){ const c=this.cross; c.classList.add('hit'); setTimeout(()=>c.classList.remove('hit'),120); }
  damageFlash(){ const e=this.dmgEl; e.style.opacity='1'; setTimeout(()=>e.style.opacity='0',260); }
  setCooldown(name,sec){
    const el=this.skillEls[name]; if(!el) return;
    const cd=el.querySelector('.cd');
    if(sec>0){ el.classList.add('cooling'); cd.textContent=sec>=1?Math.ceil(sec):''; }
    else { el.classList.remove('cooling'); cd.textContent=''; }
  }
  setUltReady(ready){ const el=this.skillEls['ultimate']; if(el) el.classList.toggle('rdy',!!ready); }
  setViewLabel(mode){
    const el=document.getElementById('viewBtnLabel');
    if(el) el.textContent = mode==='third' ? '第三人称' : '第一人称';
  }
}
