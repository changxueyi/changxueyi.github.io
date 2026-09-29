---
layout: archive
permalink: /life/
title: "生活随笔"
author_profile: true
---

<style>
.pinned-item{border-left:3px solid #d6336c;padding-left:.9em;margin-bottom:1em;}
.pinned-badge{display:inline-block;background:#d6336c;color:#fff;font-size:.7em;font-weight:700;letter-spacing:.05em;padding:.15em .7em;border-radius:1em;vertical-align:middle;margin-bottom:.15em;}
.pinned-item .archive__item-title{margin-top:.15em;}
</style>

{% assign posts = site.categories['生活随笔'] %}
{% if posts and posts.size > 0 %}
  {% assign pinned = posts | where: "pinned", true %}
  {% assign normal = posts | where_exp: "item", "item.pinned != true" %}
  {% for post in pinned %}
    <div class="pinned-item"><span class="pinned-badge">📌 置顶</span>{% include archive-single.html %}</div>
  {% endfor %}
  {% for post in normal %}
    {% include archive-single.html %}
  {% endfor %}
{% else %}
  <p>还没有「生活随笔」分类的文章。给博客文章的 Front Matter 加上 <code>categories: [生活随笔]</code> 后就会显示在这里。</p>
{% endif %}
