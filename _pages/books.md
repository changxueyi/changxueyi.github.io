---
title: "宝藏书库"
permalink: /books/
layout: archive
author_profile: true
description: "常学奕的私藏书单，像书柜一样陈列，封面即每本书的第一页，点击即可在线翻阅。"
---

<style>
.bookcase{--wood:#6f4a2f;--wood2:#8a5e3b;--wood-edge:#4a2f1c;--paper:#f3ece1;--ink:#2a2420;--muted:#7a6b5d;--accent:#9a2f2f;margin:1rem 0 0;}
.bookcase__intro{max-width:52rem;margin:0 0 1.9rem;color:#6b7280;font-size:.9rem;line-height:1.8;}
.bookcase__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2.4rem 2rem;}
.book{display:flex;flex-direction:column;}
.book__stage{position:relative;display:flex;justify-content:center;align-items:flex-end;min-height:326px;padding-bottom:16px;text-decoration:none !important;}
.book__stage::after{content:"";position:absolute;left:3%;right:3%;bottom:0;height:16px;border-radius:0 0 4px 4px;background:linear-gradient(180deg,var(--wood2),var(--wood) 55%,var(--wood-edge));box-shadow:0 12px 20px rgba(58,36,18,.3),inset 0 1px 0 rgba(255,255,255,.2);}
.book__cover{position:relative;display:block;margin-bottom:7px;border-radius:3px 7px 7px 3px;background:var(--paper);box-shadow:0 18px 30px rgba(28,20,12,.34),0 2px 6px rgba(28,20,12,.26);transition:transform .28s ease,box-shadow .28s ease;transform-origin:bottom center;}
.book__cover::before{content:"";position:absolute;top:0;bottom:0;left:0;width:9px;border-radius:3px 0 0 3px;background:linear-gradient(90deg,rgba(0,0,0,.3),rgba(0,0,0,.04) 72%,rgba(255,255,255,.14));z-index:1;}
.book__cover img{display:block;height:302px;width:auto;max-width:100%;border-radius:3px 7px 7px 3px;}
.book:hover .book__cover,.book__stage:focus-visible .book__cover{transform:translateY(-10px) rotate(-.5deg);box-shadow:0 32px 48px rgba(28,20,12,.42),0 5px 12px rgba(28,20,12,.3);}
.book__meta{margin-top:1.05rem;text-align:center;padding:0 .4rem;}
.book__title{margin:0;color:var(--ink);font-size:1.08rem;line-height:1.38;font-weight:700;letter-spacing:-.01em;}
.book__author{margin:.32rem 0 0;color:var(--muted);font-size:.76rem;letter-spacing:.03em;}
.book__blurb{margin:.52rem 0 0;color:#8a5a2b;font-size:.84rem;line-height:1.5;}
.book__read{display:inline-flex;align-items:center;gap:.3rem;margin-top:.9rem;padding:.42rem .98rem;border:1px solid rgba(154,47,47,.3);border-radius:999px;color:#9a2f2f !important;font-size:.78rem;font-weight:700;text-decoration:none !important;transition:background .15s ease,transform .15s ease;}
.book__read:hover{background:rgba(154,47,47,.08);transform:translateY(-1px);}
@media(max-width:720px){.bookcase__grid{grid-template-columns:1fr;gap:2rem;}.book__cover img{height:264px;}.book__stage{min-height:286px;}}
html[data-theme="dark"] .bookcase{--paper:#e9e1d4;}
html[data-theme="dark"] .book__title{color:#edf3f6;}
html[data-theme="dark"] .book__author{color:#9fb0b8;}
html[data-theme="dark"] .book__blurb{color:#e0a86b;}
html[data-theme="dark"] .book__read{color:#f0a0a0 !important;border-color:rgba(240,160,160,.32);}
</style>

<section class="bookcase">
  <p class="bookcase__intro">随手翻到、读完还想推荐给别人的几本书，像摆在书柜里一样陈列在这儿。封面就是每本书的第一页，点一下封面或「开始阅读」，即可在浏览器里在线翻阅。</p>
  <div class="bookcase__grid">

    <article class="book">
      <a class="book__stage" href="{{ '/files/books/how-to-live-and-earn.pdf' | relative_url }}" target="_blank" rel="noopener" aria-label="在线阅读《人，应该怎么活？应该怎么赚钱？》">
        <span class="book__cover"><img src="{{ '/images/books/how-to-live-and-earn.jpg' | relative_url }}" alt="《人，应该怎么活？应该怎么赚钱？》封面" loading="lazy"></span>
      </a>
      <div class="book__meta">
        <h3 class="book__title">人，应该怎么活？应该怎么赚钱？</h3>
        <p class="book__author">老仇 · 网络文集</p>
        <p class="book__blurb">聊透普通人的活法与赚钱</p>
        <a class="book__read" href="{{ '/files/books/how-to-live-and-earn.pdf' | relative_url }}" target="_blank" rel="noopener">开始阅读 →</a>
      </div>
    </article>

    <article class="book">
      <a class="book__stage" href="{{ '/files/books/insurance-for-life.pdf' | relative_url }}" target="_blank" rel="noopener" aria-label="在线阅读《如何用保险保障你的一生》">
        <span class="book__cover"><img src="{{ '/images/books/insurance-for-life.jpg' | relative_url }}" alt="《如何用保险保障你的一生》封面" loading="lazy"></span>
      </a>
      <div class="book__meta">
        <h3 class="book__title">如何用保险保障你的一生</h3>
        <p class="book__author">李元霸 著</p>
        <p class="book__blurb">一本书读懂保险配置逻辑</p>
        <a class="book__read" href="{{ '/files/books/insurance-for-life.pdf' | relative_url }}" target="_blank" rel="noopener">开始阅读 →</a>
      </div>
    </article>

    <article class="book">
      <a class="book__stage" href="{{ '/files/books/zhongxian-cadres.pdf' | relative_url }}" target="_blank" rel="noopener" aria-label="在线阅读《中县干部》">
        <span class="book__cover"><img src="{{ '/images/books/zhongxian-cadres.jpg' | relative_url }}" alt="《中县干部》封面" loading="lazy"></span>
      </a>
      <div class="book__meta">
        <h3 class="book__title">中县干部</h3>
        <p class="book__author">冯军旗 · 北大博士论文</p>
        <p class="book__blurb">北大博士笔下的县域官场生态</p>
        <a class="book__read" href="{{ '/files/books/zhongxian-cadres.pdf' | relative_url }}" target="_blank" rel="noopener">开始阅读 →</a>
      </div>
    </article>

    <article class="book">
      <a class="book__stage" href="{{ '/files/books/xiaozhen-xuanxiao.pdf' | relative_url }}" target="_blank" rel="noopener" aria-label="在线阅读《小镇喧嚣》">
        <span class="book__cover"><img src="{{ '/images/books/xiaozhen-xuanxiao.jpg' | relative_url }}" alt="《小镇喧嚣》封面" loading="lazy"></span>
      </a>
      <div class="book__meta">
        <h3 class="book__title">小镇喧嚣</h3>
        <p class="book__author">吴毅 著 · 三联书店</p>
        <p class="book__blurb">一个乡镇政治运作的田野实录</p>
        <a class="book__read" href="{{ '/files/books/xiaozhen-xuanxiao.pdf' | relative_url }}" target="_blank" rel="noopener">开始阅读 →</a>
      </div>
    </article>

  </div>
</section>
