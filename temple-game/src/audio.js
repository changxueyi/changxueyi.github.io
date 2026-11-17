// audio.js — ambient BGM + procedural SFX (WebAudio)
export class AudioSys {
  constructor(){
    this.ctx = null;
    this.bgm = null;
    this.master = null;
    this.ready = false;
    this.muted = false;
  }
  init(){
    if (this.ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    this.ctx = new AC();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.9;
    this.master.connect(this.ctx.destination);
    this.ready = true;
    this._startWind();
    this._startDrone();
  }
  resume(){ if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume(); }
  loadBGM(url){
    const a = new Audio();
    a.src = url; a.loop = true; a.crossOrigin = 'anonymous';
    a.volume = 0.0;
    a.preload = 'auto';
    this.bgm = a;
    this._fadeTo(0.45, 3.0);
  }
  _fadeTo(target, secs){
    if (!this.bgm) return;
    const start = this.bgm.volume, t0 = performance.now();
    const step = () => {
      const k = Math.min(1, (performance.now()-t0)/(secs*1000));
      this.bgm.volume = (start + (target-start)*k) * (this.muted?0:1);
      if (k < 1) requestAnimationFrame(step);
    };
    this.bgm.play().catch(()=>{}); step();
  }
  setMuted(m){
    this.muted = m;
    if (this.bgm) this.bgm.volume = m?0:0.45;
    if (this.master) this.master.gain.value = m?0:0.9;
  }
  // --- procedural ambience: wind + low drone ---
  _startWind(){
    const ctx = this.ctx;
    const bufSize = ctx.sampleRate * 2;
    const buf = ctx.createBuffer(1, bufSize, ctx.sampleRate);
    const d = buf.getChannelData(0);
    let last = 0;
    for (let i=0;i<bufSize;i++){ const w = Math.random()*2-1; last = (last+0.02*w)/1.02; d[i]=last*3.5; }
    const src = ctx.createBufferSource(); src.buffer = buf; src.loop = true;
    const lp = ctx.createBiquadFilter(); lp.type='lowpass'; lp.frequency.value=520;
    const g = ctx.createGain(); g.gain.value = 0.05;
    src.connect(lp).connect(g).connect(this.master); src.start();
    // slow LFO on gain
    const lfo = ctx.createOscillator(); lfo.frequency.value = 0.08;
    const lg = ctx.createGain(); lg.gain.value = 0.03;
    lfo.connect(lg).connect(g.gain); lfo.start();
  }
  _startDrone(){
    const ctx = this.ctx;
    const freqs = [55, 82.5, 110, 164.8];
    freqs.forEach((f,i)=>{
      const o = ctx.createOscillator(); o.type = i%2?'sine':'triangle'; o.frequency.value = f;
      const g = ctx.createGain(); g.gain.value = 0.012 / (i+1);
      const lfo = ctx.createOscillator(); lfo.frequency.value = 0.05 + i*0.02;
      const lg = ctx.createGain(); lg.gain.value = 0.006/(i+1);
      lfo.connect(lg).connect(g.gain); lfo.start();
      o.connect(g).connect(this.master); o.start();
    });
  }
  // --- SFX helpers ---
  _tone(freq, dur, type='sine', vol=0.3, attack=0.005){
    if (!this.ctx) return;
    const ctx=this.ctx, t=ctx.currentTime;
    const o=ctx.createOscillator(); o.type=type; o.frequency.value=freq;
    const g=ctx.createGain();
    g.gain.setValueAtTime(0,t);
    g.gain.linearRampToValueAtTime(vol, t+attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t+dur);
    o.connect(g).connect(this.master); o.start(t); o.stop(t+dur+0.05);
  }
  _noise(dur, vol=0.3, filtFreq=1000, type='lowpass'){
    if (!this.ctx) return;
    const ctx=this.ctx, t=ctx.currentTime;
    const n = Math.floor(ctx.sampleRate*dur);
    const buf = ctx.createBuffer(1,n,ctx.sampleRate);
    const d = buf.getChannelData(0);
    for(let i=0;i<n;i++) d[i]=(Math.random()*2-1)*(1-i/n);
    const src=ctx.createBufferSource(); src.buffer=buf;
    const f=ctx.createBiquadFilter(); f.type=type; f.frequency.value=filtFreq;
    const g=ctx.createGain(); g.gain.setValueAtTime(vol,t);
    g.gain.exponentialRampToValueAtTime(0.0001,t+dur);
    src.connect(f).connect(g).connect(this.master); src.start(t); src.stop(t+dur+0.02);
  }
  bell(){ // temple bell
    this._tone(196,3.2,'sine',0.35,0.01);
    this._tone(392,2.6,'sine',0.18,0.01);
    this._tone(587,1.8,'sine',0.10,0.01);
    this._tone(98,3.6,'triangle',0.15,0.02);
  }
  gong(){ this._tone(130,4.0,'triangle',0.3,0.01); this._tone(260,3.0,'sine',0.16,0.01); this._noise(0.4,0.08,800); }
  sweep(){ this._noise(0.35,0.25,2200,'highpass'); }
  punch(){ this._noise(0.12,0.4,180,'lowpass'); this._tone(70,0.12,'sine',0.25,0.002); }
  hit(){ this._noise(0.18,0.5,120,'lowpass'); this._tone(50,0.15,'square',0.2,0.002); }
  whoosh(){ this._noise(0.5,0.3,900,'bandpass'); }
  chant(){ // monk chant tone
    this._tone(110,1.6,'sawtooth',0.12,0.2);
    this._tone(220,1.6,'sine',0.08,0.2);
  }
  ult(){ this.gong(); this._noise(1.2,0.4,300,'lowpass'); this._tone(65,1.4,'sawtooth',0.3,0.05); }
  shield(){ this._tone(523,0.8,'sine',0.2,0.01); this._tone(784,0.8,'sine',0.15,0.01); }
  ui(){ this._tone(660,0.08,'square',0.08,0.002); }
  footstep(run){ this._noise(0.09, run?0.18:0.1, run?260:180,'lowpass'); }
}
