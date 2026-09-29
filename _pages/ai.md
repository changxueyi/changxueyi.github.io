---
layout: archive
permalink: /ai/
title: "AI 趋势"
author_profile: true
---

{% assign posts = site.categories['AI 趋势'] %}
{% if posts and posts.size > 0 %}
  {% for post in posts %}
    {% include archive-single.html %}
  {% endfor %}
{% else %}
  <p>还没有「AI 趋势」分类的文章。给博客文章的 Front Matter 加上 <code>categories: [AI 趋势]</code> 后就会显示在这里。</p>
{% endif %}
