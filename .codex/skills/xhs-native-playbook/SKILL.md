---
name: xhs-native-playbook
description: 小红书平台原生运营心法。用于小红书/RED/XHS 内容账号的算法节奏、发布时间、冷启动、封面点击率、标题前 3 行、搜索长尾词、评论区运营、互动提问、限流避坑和网文号起号建议。适合「和圆子一起看网文」这类内容号，不用于通用 SaaS 营销。
---

# XHS Native Playbook

Use this skill when the user wants platform-native 小红书 advice, especially for content account operations rather than generic marketing or SaaS conversion work.

## Scope

This skill covers:

- Algorithm rhythm: early traffic pools, first 2 hours, interaction speed, publishing cadence.
- Cover logic: high-CTR cover types, visual consistency, mobile-safe layout, cover pitfalls.
- Comment operations: seeded first comment, reply cadence, comment hooks, UGC reuse.
- Search traffic: long-tail keywords in title, first lines, tags, and cover text.
- Risk controls: hard-sell redirects, copied content, bait titles, machine-like comments.
- Web-novel account adaptation: book recommendation, 爽点拆解, 女性向读者, 系列化拆书.

This skill does not perform platform automation. For searching, posting, liking, collecting, commenting, or profile operations through MCP, use the `xiaohongshu` skill.

## Workflow

1. Classify the user's request:
   - **发布/冷启动**: use algorithm rhythm and publishing-window guidance.
   - **封面/标题**: use cover logic, title promise, and first-screen decision rules.
   - **评论/互动**: use golden 2-hour comment operations and low-friction question hooks.
   - **搜索/关键词**: use long-tail search traffic guidance.
   - **诊断/复盘**: evaluate CTR, saves, comments, follow conversion, and possible limit-risk.
2. Read `references/playbook.md` before giving detailed recommendations.
3. Output practical actions, not generic theory. Prefer:
   - revised titles or cover text
   - publish-time choice
   - first comment draft
   - comment hook options
   - 2-3 long-tail keywords
   - a 2-hour after-publish checklist

## Default Heuristics

- Treat the first 2 hours after posting as the decisive operating window.
- Prioritize comments over saves, saves over shares, shares over likes.
- For web-novel notes, prefer concrete type + emotional payoff + book-specific hook.
- Make covers readable in under 0.5 seconds.
- Use 2-3 specific long-tail keywords rather than broad tags only.
- Avoid fake engagement, external hard redirects, and bait-and-switch titles.

## Output Format

For a single note, return:

1. `封面/标题`
2. `正文前三行`
3. `关键词`
4. `评论区钩子`
5. `发布后 2 小时动作`

For account strategy, return:

1. `当前主要瓶颈`
2. `下 7 天动作`
3. `固定模板`
4. `数据观察点`
5. `红线提醒`
