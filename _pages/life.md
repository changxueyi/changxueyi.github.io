---
layout: archive
permalink: /life/
title: "生活随笔"
author_profile: true
---

<style>
.pinned-item{border-left:4px solid #d6336c;padding:.2em 0 .2em 1em;background:linear-gradient(90deg,rgba(214,51,108,.06),transparent);border-radius:0 6px 6px 0;}
.pinned-badge{display:inline-block;background:#d6336c;color:#fff;font-size:.62em;font-weight:700;letter-spacing:.08em;padding:.2em .7em;border-radius:1em;vertical-align:middle;position:relative;top:-2px;margin-right:.4em;}
/* 右上角「宝藏书库」小入口：定位在「生活随笔」标题右侧 */
.archive{position:relative;}
.life-books-entry{position:absolute;top:-2px;right:0;z-index:2;display:inline-flex;align-items:center;gap:.4em;padding:.4em 1em;border:1px solid rgba(154,47,47,.28);border-radius:999px;background:linear-gradient(180deg,#fff,#fbf5ef);color:#9a2f2f !important;font-size:.8rem;font-weight:700;line-height:1.1;text-decoration:none !important;box-shadow:0 2px 6px rgba(154,47,47,.08);white-space:nowrap;transition:background .15s ease,transform .15s ease,box-shadow .15s ease;}
.life-books-entry:hover,.life-books-entry:focus-visible{background:#fff;transform:translateY(-1px);box-shadow:0 6px 14px rgba(154,47,47,.16);}
@media(max-width:520px){.life-books-entry{font-size:.72rem;padding:.34em .8em;top:0;}}
html[data-theme="dark"] .life-books-entry{background:rgba(44,32,32,.6);color:#f0a0a0 !important;border-color:rgba(240,160,160,.3);}
</style>

<a class="life-books-entry" href="{{ '/books/' | relative_url }}" aria-label="进入宝藏书库"><span aria-hidden="true">📚</span> 宝藏书库 →</a>

{% assign posts = site.categories['生活随笔'] %}
{% if posts and posts.size > 0 %}
  {% assign pinned = posts | where: "pinned", true %}
  {% assign normal = posts | where_exp: "item", "item.pinned != true" %}
  {% for post in pinned %}{% include archive-single.html pinned=true %}{% endfor %}
  {% for post in normal %}{% include archive-single.html %}{% endfor %}
{% else %}
  <p>还没有「生活随笔」分类的文章。给博客文章的 Front Matter 加上 <code>categories: [生活随笔]</code> 后就会显示在这里。</p>
{% endif %}
