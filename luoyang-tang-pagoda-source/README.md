# 洛阳盛唐 · 浮空古塔

程序化体素东方幻想场景编辑器。所有建筑、地形、植被、神兽与材质均由 Three.js  geometry / Canvas 纹理生成，无外部模型或贴图依赖。

## 本地运行

```bash
npm install
npm run dev
```

打开终端输出的本地地址。

## 单文件版

```bash
npm run build:standalone
```

生成 `洛阳盛唐浮空古塔.html`。在线版由仓库根目录的 GitHub Pages 直接提供，无需服务器、无需联网。

## 性能

场景使用体素实例化、静态合批、像素比自适应和可选阴影贴图降级。软件 WebGL（无 GPU）下会自动降低分辨率；正常硬件加速浏览器可保持高画质。也可在 URL 添加 `?quality=high` 强制高画质。

## 操作

- 左键拖拽旋转、滚轮缩放、右键平移
- 双击场景或按 `R` 复位视角
- `W` 切换线框模式
- 左侧面板控制时辰、天象、风水、瀑布、Bloom、雾和阴影
- 右侧大纲选择对象、显隐、旋转与缩放
- 底栏导出约 2400px 长边 PNG 截图

## GitHub Pages 在线版

在线地址：https://changxueyi.github.io/luoyang-tang-pagoda/

仓库发布文件位于 `luoyang-tang-pagoda/index.html`，为内联 Three.js 的单文件版本；源码位于 `luoyang-tang-pagoda-source/`。
