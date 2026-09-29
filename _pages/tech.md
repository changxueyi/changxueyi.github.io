---
layout: archive
permalink: /tech/
title: "技术分享"
author_profile: true
---

{% assign posts = site.categories['技术分享'] %}
{% if posts and posts.size > 0 %}
  {% for post in posts %}
    {% include archive-single.html %}
  {% endfor %}
{% else %}
  <p>还没有「技术分享」分类的文章。给博客文章的 Front Matter 加上 <code>categories: [技术分享]</code> 后就会显示在这里。</p>
{% endif %}
