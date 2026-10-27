---
layout: archive
permalink: /life/
title: "生活随笔"
author_profile: true
---

<style>
.pinned-item{border-left:4px solid #d6336c;padding:.2em 0 .2em 1em;background:linear-gradient(90deg,rgba(214,51,108,.06),transparent);border-radius:0 6px 6px 0;}
.pinned-badge{display:inline-block;background:#d6336c;color:#fff;font-size:.62em;font-weight:700;letter-spacing:.08em;padding:.2em .7em;border-radius:1em;vertical-align:middle;position:relative;top:-2px;margin-right:.4em;}
</style>

{% assign posts = site.categories['生活随笔'] %}
{% if posts and posts.size > 0 %}
  {% assign pinned = posts | where: "pinned", true %}
  {% assign normal = posts | where_exp: "item", "item.pinned != true" %}
  {% for post in pinned %}{% include archive-single.html pinned=true %}{% endfor %}
  {% for post in normal %}{% include archive-single.html %}{% endfor %}
{% else %}
  <p>还没有「生活随笔」分类的文章。给博客文章的 Front Matter 加上 <code>categories: [生活随笔]</code> 后就会显示在这里。</p>
{% endif %}
