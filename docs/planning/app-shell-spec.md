# 超级工具平台 AppShell 开发规范 V1.0

> 最后更新：2026-06-11
> 适用项目：personal-supertool（Flask + Jinja2 + Vanilla JS）
> 所有业务页面必须运行在 AppShell 内，禁止页面自行实现导航栏

---

## 一、设计目标

AppShell 负责提供：
- 统一导航
- 统一布局
- 统一身份感
- 统一交互体验

所有业务页面必须运行在 AppShell 内，禁止页面自行实现导航栏。

---

## 二、整体布局

### 标准结构

```
┌───────────────────────────────────────────────┐
│ Header (64px)                                 │
├────────────┬──────────────────────────────────┤
│ Sidebar    │                                  │
│ (240px)    │          Page Content            │
│            │                                  │
│            │                                  │
└────────────┴──────────────────────────────────┘
```

---

### 尺寸规范

**Header**
```css
height: 64px;
border-bottom: 1px solid #E5E7EB;
background: #FFFFFF;
position: sticky;
top: 0;
z-index: 100;
```

**Sidebar**
- 展开：`width: 240px`
- 折叠：`width: 72px`

**Content**
```css
flex: 1;
overflow: auto;
padding: 24px;
max-width: none;
```

---

## 三、Header 规范

### 左侧区域 — Logo

结构：`[Logo Icon] 超级工具`

```css
font-size: 18px;
font-weight: 600;
```

### 中间区域 — 当前模块名称

显示当前模块名称，例如：选题池、生产中心、笔记库

```css
font-size: 16px;
font-weight: 500;
color: #111827;
```

可选显示版本标识：`V2 生产流水线`

### 右侧区域

统一包含：
- 通知中心（Bell icon，支持红点/未读数）
- 帮助（CircleHelp icon）
- 用户信息（头像 + 名称，点击展开个人中心/退出登录）

---

## 四、Sidebar 规范

### 一级菜单（固定顺序）

| 菜单 | Icon (lucide) | 路由 |
|------|---------------|------|
| 工作台 | LayoutDashboard | /dashboard |
| 选题池 | Library | /topic-pool |
| 生产中心 | Workflow | /production-center |
| 笔记库 | BookOpen | /note-library |
| 参考库 | Database | /reference-library |
| 数据看板 | BarChart3 | /data-dashboard |
| 系统设置 | Settings | /settings |

### 菜单样式

```css
height: 44px;
icon-size: 18px;
font-size: 14px;
font-weight: 500;
```

### 菜单状态

**默认**
```css
color: #64748B;
background: transparent;
```

**Hover**
```css
background: #F8FAFC;
color: #111827;
```

**当前激活**
```css
background: #EEF2FF;
color: #4F46E5;
```

左侧高亮条：
```css
width: 3px;
background: #4F46E5;
border-radius: 999px;
```

效果：`▍ 选题池`

---

## 五、侧边栏分组

支持分组标题：

**内容生产**
- 选题池
- 生产中心
- 笔记库
- 参考库

**运营分析**
- 数据看板

**系统管理**
- 系统设置

分组标题样式：
```css
font-size: 12px;
color: #94A3B8;
text-transform: none;
```

---

## 六、折叠模式

折叠后仅显示图标，隐藏菜单名称和分组标题。

鼠标悬停显示 Tooltip。

---

## 七、响应式规范

| 宽度 | 模式 | Sidebar |
|------|------|---------|
| >= 1440 | 标准模式 | 240px |
| 1024 ~ 1439 | 紧凑模式 | 200px |
| < 1024 | 自动折叠 | 72px |
| < 768 | 抽屉模式 | Drawer |

---

## 八、技术实现（Flask + Jinja2）

由于本项目技术栈为 Flask + Jinja2 + Vanilla JS，不是 React，实现方式如下：

### 模板结构

```
scripts/web/templates/
├── base.html           ← AppShell 骨架（Header + Sidebar + Content）
├── _header.html        ← Header 组件
├── _sidebar.html       ← Sidebar 组件
├── _nav.html           ← 已废弃，由 _sidebar.html 替代
├── topic_pool.html     ← 业务页面（只负责 Content）
└── _components/
    └── ...
```

### CSS 结构

```
scripts/static/css/
├── base.css            ← 全局变量 + AppShell 样式
├── topic_pool.css      ← 选题池页面样式
└── ...
```

### JS 结构

```
scripts/static/js/
├── app-shell.js        ← AppShell 交互（折叠/展开、Tooltip）
├── topic_pool.js       ← 选题池页面逻辑
└── ...
```

### 导航配置

在 `_sidebar.html` 中统一配置，禁止写死在业务页面中。

---

## 九、OpenCode 强制要求

1. 所有页面必须挂载在 AppShell 中
2. 禁止页面单独实现 Header
3. 禁止页面单独实现 Sidebar
4. 所有导航统一读取 `_sidebar.html`
5. 所有 Icon 使用 emoji（本项目不引入 lucide-react npm 包）
6. 所有业务页面只负责 Content 区域
