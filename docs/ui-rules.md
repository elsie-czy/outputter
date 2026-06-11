# 超级工具平台 UI Rules v1.0

> 最后更新：2026-06-11
> 本文档为全项目 UI 规范源文件。所有新页面必须遵守本文档，禁止单页面自定义设计体系。

---

## 一、设计原则

### Rule 01 — 页面服务于效率

优先级：**可读性 > 操作效率 > 视觉表现**

禁止：
- 为了填满页面增加模块
- 为了炫酷增加图表
- 为了高级增加动画

### Rule 02 — 一个页面只解决一个核心任务

| 页面 | 目标 | 禁止出现 |
|------|------|----------|
| 选题池 | 选择作品、提交生产 | 拆文结果、评分报告、生图结果 |
| 生产中心 | 查看结果、审核结果 | 选题筛选、批量导入 |
| 知识库 | 浏览子库、查看条目 | 生产任务、发布操作 |
| 数据中心 | 效果统计、趋势分析 | 拆文操作、笔记编辑 |

---

## 二、布局规范

### Rule 03 — 统一 Dashboard Layout

```
┌─ Header (56px) ──────────────────────────────────────┐
│  Logo                       导航项 × N               │
├─ Content ────────────────────────────────────────────┤
│  顶部统计栏 (KPI Cards)                               │
│  ┌──────────────────────────────────────────────────┐│
│  │  主工作区                                        ││
│  │                                                  ││
│  └──────────────────────────────────────────────────┘│
│  底部操作区（可选）                                    │
└──────────────────────────────────────────────────────┘
```

```css
max-width: 1600px;
padding: 24px;
gap: 16px;     /* 模块间距 */
```

禁止：页面内容顶边贴死、模块间距忽大忽小

---

## 三、卡片规范

### Rule 04 — 统一 Card 样式

```css
background: #fff;
border: 1px solid #e5e7eb;
border-radius: 12px;
padding: 16px;
```

Hover：
```css
box-shadow: 0 4px 12px rgba(0,0,0,0.08);
```

**统一 12px 圆角**，禁止 8px/16px/20px 混用。

---

## 四、颜色规范

### Rule 05 — 品牌主色

```css
--color-primary: #3B82F6;     /* 主按钮、选中、激活 */
--color-success: #22C55E;     /* 成功状态（保持绿色，区分操作激活和结果成功） */
```

### Rule 06 — 辅助色

```css
--color-success: #22C55E;
--color-warning: #F59E0B;
--color-error:   #EF4444;
--color-info:    #3B82F6;
```

### 背景与文字

```css
--bg-page:      #F9FAFB;
--bg-card:      #FFFFFF;
--text-primary: #111827;
--text-secondary: #6B7280;
--text-muted:   #94A3B8;
--border:       #E5E7EB;
```

禁止：渐变色、彩虹色、页面出现超过 5 种主题色。

---

## 五、字体规范

### Rule 07 — 仅使用 Inter / PingFang SC

```css
font-family: Inter, PingFang SC, sans-serif;
```

| 层级 | 字号 | 字重 | 用途 |
|------|------|------|------|
| 页面标题 | 24px | 600 | 页面顶部 H1 |
| 模块标题 | 18px | 600 | 卡片/区块标题 |
| 正文 | 14px | 400 | 主体内容 |
| 辅助信息 | 12px | 400 | 时间、来源、标签 |

禁止：11px/13px/15px/17px/19px 随机出现。

---

## 六、KPI 规范

### Rule 08 — 顶部统计卡统一

```
┌───────────────────┐
│  56               │  ← 数值 (24px 600)
│  待拆作品          │  ← 标题 (12px 400)
│  ↑12%              │  ← 趋势 (12px)
└───────────────────┘
     220 × 100px
```

禁止：有的卡片带图标有的不带、有的高 100px 有的高 140px。

---

## 七、列表规范

### Rule 09 — 统一列表顺序

```
☐ 选择  │  主信息  │  辅助信息  │  状态
```

示例：
```
☐ │ 废材小姐被退婚后  │ 起点·都市  │ 生产中
```

禁止：主信息放右边、状态放中间、辅助信息在顶部。

---

## 八、状态规范

### Rule 10 — 全系统统一 5 状态

| 状态 | 英文 | 颜色 | 说明 |
|------|------|------|------|
| 待处理 | pending | #94A3B8 | 队列等待 |
| 生产中 | processing | #3B82F6 | 正在拆文/生成 |
| 待审核 | review | #F59E0B | 需人工确认 |
| 已完成 | completed | #22C55E | 可发布 |
| 失败 | failed | #EF4444 | 需重试 |

禁止：进行中/执行中/分析中/运行中 混用。统一"生产中"。

---

## 九、按钮规范

### Rule 11 — 三级按钮体系

| 级别 | 样式 | 用途 |
|------|------|------|
| Primary | 蓝紫底白字 `bg:#3B82F6` | 提交生产、开始拆文、生成图片 |
| Secondary | 白底灰边 `bg:#fff border:#e5e7eb` | 取消、返回、查看详情 |
| Danger | 红底白字 `bg:#EF4444` | 删除、终止任务 |

**页面只能有 1 个主按钮**。禁止一个区域出现 3 个绿色按钮。

---

## 十、空状态规范

### Rule 12 — 必须有 Empty State

```
┌─────────────────────────────────┐
│         📋                      │
│   暂无待处理作品                  │
│   请先同步飞书选题库              │
│                                 │
│       [立即同步]                 │
└─────────────────────────────────┘
```

禁止：列表为空时显示空白。

---

## 十一、生产中心规范

### Rule 13 — 默认展示笔记内容

最终产物是笔记，拆文只是过程。展示优先级：

```
笔记内容 > 评分报告 > 拆文结果 > 修改记录
```

---

## 十二、信息密度规范

### Rule 14 — 最多 3 层信息

```
一级: 选题
  ↓
二级: 分类
  ↓
三级: 评分
```

禁止一堆信息堆在一个页面上。

---

## 十三、AI 产品特殊规范

### Rule 15 — AI 过程隐藏

不默认展示 Prompt/Temperature/TopP/Token 等 AI 参数。

放到「高级信息」折叠区。

默认展示：结果、评分、建议。

---

## 十四、未来页面统一结构

所有业务页面对齐：

```
顶部统计区 (KPI Cards)
  ↓
主工作区
  ↓
操作区
```

---

## 十五、Icon 规范

### Rule 16 — 全项目统一使用 emoji + SVG

> 注意：本项目技术栈是 Flask + Jinja2 模板 + Vanilla JS，**不使用 React / shadcn / Tailwind**。
> 不能引入 npm 包。图标方案采用 emoji 文本 + 少量 SVG 内联。

### 图标方式

```
默认场景:   Unicode emoji（&#x 编码直接嵌入 HTML）
动态状态:   纯 CSS 实现（.status-dot 圆点 + 颜色）
装饰图标:   手写 SVG（少量，放 _components/ 目录）
```

**禁止引入任何图标库**（lucide-react / heroicons / font-awesome / iconfont / antd-icons 等）。

### emoji 图标映射

```text
工作台       🏠   &#x1F3E0;
拆文中心     🔧   &#x1F527;
笔记生成     📝   &#x1F4DD;
知识库       📚   &#x1F4DA;
视频脚本     🎬   &#x1F3AC;
数据中心     📊   &#x1F4CA;
系统设置     ⚙️   &#x2699;&#xFE0F;
选题池       📖   &#x1F4D6;
生产中心     ⚡   &#x26A1;
发布管理     📤   &#x1F4E4;

待处理  ○   (纯 CSS circle)
生产中  ◉   (纯 CSS circle + pulse 动画)
待审核  ◐   (纯 CSS half-circle)
已完成  ✓   (纯字符)
失败    ✗   (纯字符)

搜索      🔍
筛选      ☰
添加      +
导出      ⬇
```

### 图标尺寸

| 场景 | 字号 | 用途 |
|------|------|------|
| 导航菜单 | 16px | `font-size: 16px` |
| 卡片标题 | 32px | `font-size: 32px` |
| 按钮内 | 14px | `font-size: 14px` |
| KPI 卡片 | 24px | `font-size: 24px` |
| 空状态 | 48px | `font-size: 48px` |

---

## 十六、实现要求

### 技术栈（再次强调）

```
后端:   Python 3.11 + Flask + Gunicorn
前端:   Jinja2 模板 + Vanilla JS + 手写 CSS
构建:   无（纯静态，无 webpack/vite/npm）
包管理: pip + requirements.txt + .venv
```

**不使用**：React / Vue / Next.js / shadcn/ui / TailwindCSS / npm / lucide-react。

### CSS 变量定义

全部颜色和尺寸从 `:root` 中取，禁止在组件中硬编码：

```css
:root {
  --color-primary: #3B82F6;
  --color-success: #22C55E;
  --color-warning: #F59E0B;
  --color-error: #EF4444;
  --color-info: #3B82F6;
  --bg-page: #F9FAFB;
  --bg-card: #FFFFFF;
  --text-primary: #111827;
  --text-secondary: #6B7280;
  --text-muted: #94A3B8;
  --border: #E5E7EB;
  --radius: 12px;
  --font-family: Inter, PingFang SC, sans-serif;
  --gap: 16px;
}
```

### Jinja2 模板组件

```
scripts/web/templates/_components/
  kpi_card.html          ← 统计卡片
  status_tag.html         ← 状态标签（替代 status_badge）
  empty_state.html        ← 空状态
  page_header.html        ← 页面头部
  action_bar.html         ← 操作栏
  score_bar.html          ← 评分进度条
  toast.html              ← Toast 通知
```

**命名**：全部 `snake_case`，与现有组件命名一致。

### 开发纪律

- 所有新页面必须遵守 `docs/ui-rules.md`
- 禁止单页面自定义设计体系
- 所有组件优先复用 `templates/_components/`
- 颜色禁止硬编码，必须用 `var(--color-*)`
- 字号禁止非标准值（24/18/14/12 以外）
