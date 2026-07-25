---
kind: frontend_style
name: Tailwind CSS + Font Awesome 前端样式体系
category: frontend_style
scope:
    - '**'
source_files:
    - frontend/src/style.css
    - frontend/src/assets/fa-all.css
    - frontend/vite.config.ts
    - frontend/package.json
---

## 1. 使用的系统/方法
- **CSS 框架**：Tailwind CSS v4（通过 `@tailwindcss/vite` 插件在 Vite 中启用），采用 `@import "tailwindcss"` 的 v4 导入方式。
- **图标库**：Font Awesome 7.3.0，通过本地 `src/assets/fa-all.css` 引入完整字体与动画，配套 `public/webfonts/` 下的 woff2 字体文件。
- **构建工具**：Vite 8，配合 `@vitejs/plugin-vue` 和 `@tailwindcss/vite` 插件链。
- **国际化样式**：无独立主题切换机制，样式直接写在 CSS/组件内联类名中。

## 2. 核心文件与包
- `frontend/src/style.css` — 全局样式入口，包含 Tailwind 导入、基础重置、滚动条与选区样式。
- `frontend/src/assets/fa-all.css` — Font Awesome 全量样式与字体映射。
- `frontend/vite.config.ts` — 配置 Tailwind 插件、开发服务器代理（`/api` → `http://localhost:8000`）。
- `frontend/package.json` — 声明 `tailwindcss`、`@tailwindcss/vite`、`vue-i18n` 等依赖。
- `frontend/public/webfonts/` — 字体资源（fa-brands、fa-regular、fa-solid、fa-v4compatibility）。

## 3. 架构与约定
- **样式组织**：单一全局样式文件 `style.css` 通过 `@import "tailwindcss"` 注入 Tailwind，再集中定义 `html`、`body`、`:focus-visible`、滚动条、`::selection` 等全局规则。
- **组件级样式**：各 Vue 组件使用 Tailwind 原子类直接在模板中编写样式，未使用 `<style scoped>` 或外部 CSS 模块。
- **响应式策略**：完全依赖 Tailwind 的响应式前缀（如 `sm:`、`md:`、`lg:`），无自定义媒体查询。
- **设计令牌**：通过 Tailwind 内置颜色命名空间（如 `colors.violet.400`、`colors.stone.200`）作为设计令牌，未在 `tailwind.config` 中扩展自定义主题。
- **字体策略**：`body` 使用系统字体栈（system-ui、PingFang SC、Microsoft YaHei 等），图标统一走 Font Awesome 类名。

## 4. 约定与约束
- **必须通过 Tailwind 原子类实现布局与样式**：所有组件均直接使用 Tailwind 类名，未见手写 CSS 类（除全局 reset）。
- **图标统一使用 Font Awesome 类名**：组件中通过 `fa-*` 类调用图标，禁止自行引入 SVG 图标。
- **全局样式仅允许在 `style.css` 中修改**：滚动条、选区、焦点可见性等浏览器默认样式覆盖集中在该文件。
- **开发代理约定**：所有 `/api` 请求通过 Vite dev server 代理到后端 `http://localhost:8000`，并开启 WebSocket 支持。
- **无暗色模式/主题切换**：未发现 `dark:` 变体或主题配置文件，样式为单色调方案。
- **无 CSS-in-JS 或预处理器**：项目未引入 Sass/Less/Stylus，纯原生 CSS + Tailwind。