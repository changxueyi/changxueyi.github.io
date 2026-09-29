---
layout: archive
permalink: /life/
title: "生活随笔"
author_profile: true
---

{% assign posts = site.categories['生活随笔'] %}
{% if posts and posts.size > 0 %}
  {% for post in posts %}
    {% include archive-single.html %}
  {% endfor %}
{% else %}
  <p>还没有「生活随笔」分类的文章。给博客文章的 Front Matter 加上 <code>categories: [生活随笔]</code> 后就会显示在这里。</p>
{% endif %}
