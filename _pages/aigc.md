---
title: "AIGC 作品"
permalink: /aigc/
layout: archive
author_profile: true
description: "常学奕用 AI 生成的作品陈列馆：AI 视频、AI 图片与 AI 网页，像货架一样分区展示，点击即可在线播放或预览。"
---

<style>
.aigc{--wood:#6f4a2f;--wood2:#8a5e3b;--wood-edge:#4a2f1c;--wood-lip:#5c3c25;--paper:#f6f1e8;--ink:#2a2420;--muted:#857567;--accent:#9a2f2f;
  margin:1rem 0 0;padding:2rem 1.9rem 2.4rem;border:1px solid rgba(120,80,45,.18);border-radius:16px;
  background:linear-gradient(180deg,#fbf7f0,#f3ece0);box-shadow:inset 0 1px 0 rgba(255,255,255,.6),0 12px 32px rgba(74,47,28,.08);}
.aigc__intro{max-width:52rem;margin:0 0 1.6rem;color:#6b7280;font-size:.9rem;line-height:1.8;}
.aigc-cat{margin-top:2.2rem;}
.aigc-cat:first-of-type{margin-top:.4rem;}
.aigc-cat__head{display:flex;align-items:baseline;gap:.7rem;margin:0 0 1.4rem;padding-bottom:.6rem;border-bottom:1px dashed rgba(120,80,45,.3);}
.aigc-cat__index{font-family:"SFMono-Regular",Consolas,monospace;font-size:.82rem;font-weight:700;color:var(--accent);letter-spacing:.06em;}
.aigc-cat__title{margin:0;color:var(--ink);font-size:1.18rem;font-weight:800;letter-spacing:-.01em;}
.aigc-cat__count{margin-left:auto;color:var(--muted);font-size:.76rem;letter-spacing:.03em;}
.aigc-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.3rem 2rem;}
.aigc-card{display:flex;flex-direction:column;align-items:center;}
.aigc-card__stage{position:relative;display:flex;justify-content:center;align-items:flex-end;width:100%;padding-bottom:15px;cursor:pointer;text-decoration:none !important;background:none;border:0;}
.aigc-card__stage::after{content:"";position:absolute;left:4%;right:4%;bottom:0;height:14px;border-radius:2px;
  background:linear-gradient(180deg,var(--wood2),var(--wood) 60%,var(--wood-edge));
  box-shadow:0 11px 17px rgba(58,36,18,.26),inset 0 1px 0 rgba(255,255,255,.22),inset 0 -2px 0 var(--wood-lip);}
.aigc-card__screen{position:relative;width:100%;aspect-ratio:16/9;margin-bottom:6px;border-radius:7px;overflow:hidden;
  background:#14100c;border:1px solid rgba(60,40,24,.26);
  box-shadow:0 16px 26px rgba(28,20,12,.3),0 2px 5px rgba(28,20,12,.22);transition:transform .28s ease,box-shadow .28s ease;transform-origin:bottom center;}
.aigc-card__screen img{width:100%;height:100%;object-fit:cover;display:block;}
.aigc-card__screen::after{content:"";position:absolute;inset:0;pointer-events:none;border-radius:inherit;box-shadow:inset 0 0 0 1px rgba(255,255,255,.14);background:linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.28));}
.aigc-card__play{position:absolute;top:50%;left:50%;z-index:2;transform:translate(-50%,-50%);width:58px;height:58px;border-radius:999px;
  display:grid;place-items:center;background:rgba(20,16,12,.52);border:1.5px solid rgba(255,255,255,.85);color:#fff;font-size:20px;padding-left:4px;
  backdrop-filter:blur(2px);transition:transform .2s ease,background .2s ease;}
.aigc-card:hover .aigc-card__screen,.aigc-card__stage:focus-visible .aigc-card__screen{transform:translateY(-10px);box-shadow:0 30px 44px rgba(28,20,12,.4),0 5px 12px rgba(28,20,12,.28);}
.aigc-card:hover .aigc-card__play{transform:translate(-50%,-50%) scale(1.08);background:var(--accent);}
.aigc-card__dur{position:absolute;right:8px;bottom:8px;z-index:2;padding:.12rem .42rem;border-radius:5px;background:rgba(20,16,12,.72);color:#fff;font-size:.68rem;letter-spacing:.03em;}
.aigc-card__meta{margin-top:1.05rem;text-align:center;max-width:22rem;}
.aigc-card__title{margin:0;color:var(--ink);font-size:1.02rem;line-height:1.4;font-weight:700;letter-spacing:-.01em;}
.aigc-card__sub{margin:.3rem 0 0;color:var(--muted);font-size:.75rem;letter-spacing:.03em;}
.aigc-card__blurb{margin:.5rem 0 0;color:#9a6a2e;font-size:.82rem;line-height:1.5;}
.aigc-card__btn{display:inline-flex;align-items:center;gap:.3rem;margin-top:.85rem;padding:.4rem .98rem;border:1px solid rgba(154,47,47,.28);border-radius:999px;color:#9a2f2f !important;font-size:.76rem;font-weight:700;text-decoration:none !important;transition:background .15s ease,transform .15s ease,box-shadow .15s ease;}
.aigc-card__btn:hover{background:rgba(154,47,47,.07);transform:translateY(-1px);box-shadow:0 4px 10px rgba(154,47,47,.12);}
.aigc-empty{grid-column:1/-1;position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.5rem;min-height:150px;padding:2rem;
  border:1px dashed rgba(120,80,45,.34);border-radius:10px;background:rgba(255,255,255,.4);color:var(--muted);}
.aigc-empty strong{color:var(--ink);font-size:.98rem;font-weight:700;}
.aigc-empty span{font-size:.8rem;}
</style>

<style>
.aigc-lightbox{position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;padding:4vmin;
  background:rgba(12,9,6,.82);backdrop-filter:blur(6px);}
.aigc-lightbox.is-open{display:flex;}
.aigc-lightbox__frame{position:relative;width:min(1100px,96vw);max-height:90vh;aspect-ratio:16/9;background:#000;border-radius:10px;overflow:hidden;
  box-shadow:0 30px 80px rgba(0,0,0,.6);}
.aigc-lightbox__frame video{width:100%;height:100%;display:block;background:#000;}
.aigc-lightbox__close{position:absolute;top:calc(4vmin - 6px);right:calc(4vmin - 6px);width:44px;height:44px;border-radius:999px;
  border:1.5px solid rgba(255,255,255,.7);background:rgba(20,16,12,.6);color:#fff;font-size:24px;line-height:1;cursor:pointer;
  display:grid;place-items:center;transition:background .18s ease,transform .18s ease;}
.aigc-lightbox__close:hover{background:var(--accent,#9a2f2f);transform:scale(1.06);}
@media(max-width:720px){
  .aigc{padding:1.4rem 1.1rem 1.8rem;}
  .aigc-grid{grid-template-columns:1fr;gap:.4rem;}
  .aigc-card{margin-bottom:1.6rem;}
  .aigc-lightbox__close{top:2vmin;right:2vmin;}
}
html[data-theme="dark"] .aigc{background:linear-gradient(180deg,rgba(40,30,20,.5),rgba(28,20,12,.55));border-color:rgba(188,150,110,.22);box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 12px 32px rgba(0,0,0,.3);}
html[data-theme="dark"] .aigc__intro{color:#adbbc3;}
html[data-theme="dark"] .aigc-cat__title{color:#edf3f6;}
html[data-theme="dark"] .aigc-cat__head{border-bottom-color:rgba(188,150,110,.3);}
html[data-theme="dark"] .aigc-card__title{color:#edf3f6;}
html[data-theme="dark"] .aigc-card__sub{color:#9fb0b8;}
html[data-theme="dark"] .aigc-card__blurb{color:#e0a86b;}
html[data-theme="dark"] .aigc-card__btn{color:#f0a0a0 !important;border-color:rgba(240,160,160,.32);}
html[data-theme="dark"] .aigc-empty{background:rgba(255,255,255,.04);border-color:rgba(188,150,110,.3);color:#9fb0b8;}
html[data-theme="dark"] .aigc-empty strong{color:#edf3f6;}
</style>

<section class="aigc">
  <p class="aigc__intro">这里陈列用 AI 做出来的作品，像货架一样按类别摆放：AI 视频、AI 图片、AI 网页。点一下封面或「播放 / 预览」即可直接在页面里打开，无需下载。</p>

  <div class="aigc-cat">
    <div class="aigc-cat__head">
      <span class="aigc-cat__index">01</span>
      <h3 class="aigc-cat__title">AI 视频板块</h3>
      <span class="aigc-cat__count">3 个作品</span>
    </div>
    <div class="aigc-grid">

      <article class="aigc-card">
        <a class="aigc-card__stage" href="{{ '/files/aigc/baicaoyuan.mp4' | relative_url }}" data-video="{{ '/files/aigc/baicaoyuan.mp4' | relative_url }}" data-title="《从百草园到三味书屋》3D 课本朗读" target="_blank" rel="noopener" aria-label="播放《从百草园到三味书屋》3D 课本朗读">
          <span class="aigc-card__screen">
            <img src="{{ '/images/aigc/baicaoyuan.jpg' | relative_url }}" alt="《从百草园到三味书屋》3D 课本朗读 封面" loading="lazy">
            <span class="aigc-card__dur">50 秒</span>
          </span>
          <span class="aigc-card__play" aria-hidden="true">▶</span>
        </a>
        <div class="aigc-card__meta">
          <h4 class="aigc-card__title">从百草园到三味书屋</h4>
          <p class="aigc-card__sub">3D 课本朗读 · 鲁迅</p>
          <p class="aigc-card__blurb">立体课本翻到课文，镜头逐句红色高亮，男声播音腔朗读。</p>
          <a class="aigc-card__btn" href="{{ '/files/aigc/baicaoyuan.mp4' | relative_url }}" data-video="{{ '/files/aigc/baicaoyuan.mp4' | relative_url }}" data-title="《从百草园到三味书屋》3D 课本朗读" target="_blank" rel="noopener">▶ 播放</a>
        </div>
      </article>

      <article class="aigc-card">
        <a class="aigc-card__stage" href="{{ '/files/aigc/beiying.mp4' | relative_url }}" data-video="{{ '/files/aigc/beiying.mp4' | relative_url }}" data-title="《背影》3D 课本朗读" target="_blank" rel="noopener" aria-label="播放《背影》3D 课本朗读">
          <span class="aigc-card__screen">
            <img src="{{ '/images/aigc/beiying.jpg' | relative_url }}" alt="《背影》3D 课本朗读 封面" loading="lazy">
            <span class="aigc-card__dur">40 秒</span>
          </span>
          <span class="aigc-card__play" aria-hidden="true">▶</span>
        </a>
        <div class="aigc-card__meta">
          <h4 class="aigc-card__title">背影</h4>
          <p class="aigc-card__sub">3D 课本朗读 · 朱自清</p>
          <p class="aigc-card__blurb">从封面展开到课文，逐句跟读买橘子的一段，温厚男声。</p>
          <a class="aigc-card__btn" href="{{ '/files/aigc/beiying.mp4' | relative_url }}" data-video="{{ '/files/aigc/beiying.mp4' | relative_url }}" data-title="《背影》3D 课本朗读" target="_blank" rel="noopener">▶ 播放</a>
        </div>
      </article>

      <article class="aigc-card">
        <a class="aigc-card__stage" href="{{ '/files/aigc/111.mp4' | relative_url }}" data-video="{{ '/files/aigc/111.mp4' | relative_url }}" data-title="AI 概念短片 · 智能驾驶 HUD" target="_blank" rel="noopener" aria-label="播放 AI 概念短片 · 智能驾驶 HUD">
          <span class="aigc-card__screen">
            <img src="{{ '/images/aigc/111.jpg' | relative_url }}" alt="AI 概念短片 · 智能驾驶 HUD 封面" loading="lazy">
            <span class="aigc-card__dur">12 秒</span>
          </span>
          <span class="aigc-card__play" aria-hidden="true">▶</span>
        </a>
        <div class="aigc-card__meta">
          <h4 class="aigc-card__title">智能驾驶 HUD</h4>
          <p class="aigc-card__sub">AI 概念短片</p>
          <p class="aigc-card__blurb">黄昏公路上的第一视角，抬头显示实时车速与路况。</p>
          <a class="aigc-card__btn" href="{{ '/files/aigc/111.mp4' | relative_url }}" data-video="{{ '/files/aigc/111.mp4' | relative_url }}" data-title="AI 概念短片 · 智能驾驶 HUD" target="_blank" rel="noopener">▶ 播放</a>
        </div>
      </article>

    </div>
  </div>

  <div class="aigc-cat">
    <div class="aigc-cat__head">
      <span class="aigc-cat__index">02</span>
      <h3 class="aigc-cat__title">AI 图片板块</h3>
      <span class="aigc-cat__count">整理中</span>
    </div>
    <div class="aigc-grid">
      <div class="aigc-empty">
        <strong>敬请期待 · 作品整理中</strong>
        <span>AI 生成的海报、插画与封面即将上架。</span>
      </div>
    </div>
  </div>

  <div class="aigc-cat">
    <div class="aigc-cat__head">
      <span class="aigc-cat__index">03</span>
      <h3 class="aigc-cat__title">AI 网页板块</h3>
      <span class="aigc-cat__count">整理中</span>
    </div>
    <div class="aigc-grid">
      <div class="aigc-empty">
        <strong>敬请期待 · 作品整理中</strong>
        <span>AI 搭建的交互网页与小应用即将上架，也可先逛 <a href="{{ '/experience/' | relative_url }}">在线体验</a>。</span>
      </div>
    </div>
  </div>
</section>

<div class="aigc-lightbox" id="aigcLightbox" aria-hidden="true" role="dialog" aria-modal="true" aria-label="视频播放">
  <button class="aigc-lightbox__close" type="button" id="aigcClose" aria-label="关闭播放">×</button>
  <div class="aigc-lightbox__frame">
    <video id="aigcVideo" controls playsinline preload="metadata"></video>
  </div>
</div>

<script>
(function(){
  var box=document.getElementById('aigcLightbox'),
      vid=document.getElementById('aigcVideo'),
      closeBtn=document.getElementById('aigcClose');
  if(!box||!vid){return;}
  function open(src,title){
    vid.src=src; if(title){vid.setAttribute('aria-label',title);} 
    box.classList.add('is-open'); box.setAttribute('aria-hidden','false');
    document.body.style.overflow='hidden';
    var p=vid.play(); if(p&&p.catch){p.catch(function(){});}
  }
  function close(){
    box.classList.remove('is-open'); box.setAttribute('aria-hidden','true');
    document.body.style.overflow=''; vid.pause();
    vid.removeAttribute('src'); vid.load();
  }
  document.querySelectorAll('[data-video]').forEach(function(el){
    el.addEventListener('click',function(e){
      e.preventDefault();
      open(el.getAttribute('data-video'), el.getAttribute('data-title'));
    });
  });
  closeBtn.addEventListener('click',close);
  box.addEventListener('click',function(e){ if(e.target===box){close();} });
  document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&box.classList.contains('is-open')){close();} });
})();
</script>
