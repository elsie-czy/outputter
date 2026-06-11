import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from html import unescape

import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.utils import append_jsonl, now_ts
from scripts.config import PATHS, ensure_dirs


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"


def _now_ms():
    return int(time.time() * 1000)


def _clean_ws(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _parse_count_text(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(float(s))
    t = str(s).strip().replace(",", "").replace("+", "")
    if not t:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    v = float(m.group(1))
    if "万" in t:
        v *= 10000
    elif "亿" in t:
        v *= 100000000
    return int(v)


def fetch_fanqie_rank(limit=30):
    """
    Fanqie rank page uses obfuscated font for list text, but the /page/<id> detail page has real title/author.
    Strategy:
      1) Fetch /rank and extract page ids
      2) Fetch each /page/<id> and parse <title> and meta keywords/description
    """
    out = []
    limit = int(limit or 30)

    # Fanqie provides many rank category pages; we sample multiple pages to build enough unique ids.
    entry_url = "https://fanqienovel.com/rank"
    entry_html = requests.get(entry_url, headers={"User-Agent": UA}, timeout=20).text
    rank_paths = ["/rank"]
    # Pull a deterministic subset of rank category pages (keeps runtime bounded).
    more = sorted(set(re.findall(r'href=\"(/rank/[0-9_]+)\"', entry_html)))[:40]
    rank_paths.extend(more)

    seen = set()
    page_ids = []
    page_meta = {}  # pid -> rank_source
    page_stats = {}  # pid -> {"inread_text": str, "inread_num": int|None}
    for path in rank_paths:
        if len(page_ids) >= limit:
            break
        url = f"https://fanqienovel.com{path}" if path != "/rank" else entry_url
        try:
            html = requests.get(url, headers={"User-Agent": UA}, timeout=20).text
        except Exception:
            continue
        # Extract per-item block to capture in-read count (unobfuscated).
        blocks = re.split(r'<div class=\"rank-book-item\">', html)
        ids = []
        for b in blocks[1:]:
            m = re.search(r'href=\"/page/(\d+)\"', b)
            if not m:
                continue
            pid = m.group(1)
            ids.append(pid)
            # in-read count: 在读：<!-- -->39.6万
            m2 = re.search(r'在读：<!-- -->\s*([^<]{1,20})<', b)
            inread_text = _clean_ws(m2.group(1)) if m2 else ""
            inread_num = _parse_count_text(inread_text) if inread_text else None
            page_stats.setdefault(pid, {})
            if inread_text and "inread_text" not in page_stats[pid]:
                page_stats[pid]["inread_text"] = inread_text
                page_stats[pid]["inread_num"] = inread_num

        for pid in ids:
            if pid in seen:
                continue
            seen.add(pid)
            page_ids.append(pid)
            page_meta[pid] = f"番茄小说-{path}"
            if len(page_ids) >= limit:
                break

    for idx, pid in enumerate(page_ids, 1):
        url = f"https://fanqienovel.com/page/{pid}"
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        text = resp.text
        m = re.search(r"<title>(.*?)</title>", text, flags=re.S)
        title_tag = _clean_ws(unescape(m.group(1)) if m else "")
        # Example: 惹金枝完整版在线免费阅读_惹金枝小说_番茄小说官网
        title = title_tag.split("完整版在线免费阅读", 1)[0] if title_tag else ""
        title = title.split("_", 1)[0].strip()
        kw = ""
        m = re.search(r'<meta[^>]+name=\"keywords\"[^>]+content=\"([^\"]+)\"', text, flags=re.I)
        if m:
            kw = _clean_ws(unescape(m.group(1)))
        author = ""
        if kw and title:
            parts = [p.strip() for p in kw.split(",") if p.strip()]
            # Common pattern: "{author}小说{title}"
            for p in parts:
                if p.endswith(f"小说{title}") and len(p) <= 60:
                    author = p[: -len(f"小说{title}")].strip()
                    break
            if not author:
                # Fallback: "... {author}小说{title}" may appear with extra prefix
                for p in parts:
                    m2 = re.search(rf"([^,]{1,30})小说{re.escape(title)}$", p)
                    if m2:
                        author = m2.group(1).strip()
                        break
        if not author:
            # fallback: title includes "..._..._番茄小说官网", try find "作者" nearby
            m3 = re.search(r"作者[:：]\s*([^<\\s]{1,30})", text)
            if m3:
                author = m3.group(1).strip()
        desc = ""
        m = re.search(r'<meta[^>]+name=\"description\"[^>]+content=\"([^\"]+)\"', text, flags=re.I)
        if m:
            desc = _clean_ws(unescape(m.group(1)))
        finish = "未知"
        if "已完结" in text:
            finish = "完结"
        elif "连载" in text:
            finish = "连载"
        # Categories/tags
        cats = re.findall(r'<span class=\"info-label-grey\">([^<]{1,30})</span>', text)
        cats = [_clean_ws(unescape(c)) for c in cats if _clean_ws(c)]
        inread_text = (page_stats.get(pid) or {}).get("inread_text", "")
        inread_num = (page_stats.get(pid) or {}).get("inread_num", None)
        heat = float(inread_num) if isinstance(inread_num, int) and inread_num > 0 else float(
            max(1, (len(page_ids) - idx + 1))
        )

        out.append(
            {
                "platform": "番茄",
                "title": title or "",
                "author": author or "",
                "link": url,
                "type": " / ".join(cats[:4]) if cats else "",
                "rank_source": page_meta.get(pid) or "番茄小说-排行榜",
                "rank_pos": idx,
                # heat derived from rank position; larger is better
                "heat": heat,
                "reason": f"来自番茄排行榜，第{idx}名",
                "desc": desc[:400] if desc else "",
                "finish": finish,
                "inread_text": inread_text,
                "inread_num": inread_num,
            }
        )
    return out


def fetch_jjwxc_topten(limit=30):
    """
    Fetch JJWXC topten page (GBK) and parse novelid + author.
    """
    out = []
    url = "https://www.jjwxc.net/topten.php"
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    resp.encoding = "gbk"
    text = resp.text

    # Parse by proximity: book link then nearest author link.
    pairs = []
    for m in re.finditer(
        r'onebook\.php\?novelid=(\d+)"[^>]*>\s*([^<]{1,80})\s*</a>',
        text,
        flags=re.S,
    ):
        novelid = m.group(1)
        title = m.group(2)
        tail = text[m.end() : m.end() + 600]
        ma = re.search(
            r'oneauthor\.php\?authorid=(\d+)"[^>]*>\s*([^<]{1,40})\s*</a>',
            tail,
            flags=re.S,
        )
        if not ma:
            continue
        aid = ma.group(1)
        author = ma.group(2)
        pairs.append((novelid, title, aid, author))
    seen = set()
    for (novelid, title, _aid, author) in pairs:
        title = _clean_ws(title).strip("《》")
        author = _clean_ws(author)
        key = (title, author)
        if key in seen:
            continue
        seen.add(key)
        rank_pos = len(out) + 1
        # Fetch detail for description and stats.
        desc = ""
        finish = "未知"
        collect_n = None
        review_n = None
        score_n = None  # use 文章积分 as platform score
        try:
            d = requests.get(
                f"https://www.jjwxc.net/onebook.php?novelid={novelid}",
                headers={"User-Agent": UA},
                timeout=20,
            )
            d.encoding = "gbk"
            dt = d.text
            # description
            mdesc = re.search(r'id=\"novelintro\"[^>]*>(.*?)</div>', dt, flags=re.S)
            if mdesc:
                raw = mdesc.group(1)
                raw = re.sub(r"<img[^>]*>", " ", raw)
                raw = re.sub(r"<br\\s*/?>", "\n", raw, flags=re.I)
                raw = re.sub(r"<[^>]+>", " ", raw)
                desc = _clean_ws(unescape(raw))
            # finish
            mfin = re.search(r'itemprop=\"updataStatus\"[^>]*>\s*<font[^>]*>([^<]{1,10})<', dt, flags=re.S)
            if mfin and "完结" in mfin.group(1):
                finish = "完结"
            elif mfin:
                finish = "连载"
            # counts
            mrev = re.search(r'itemprop=\"reviewCount\"[^>]*>(\d{1,12})<', dt)
            mcol = re.search(r'itemprop=\"collectedCount\"[^>]*>(\d{1,12})<', dt)
            if mrev:
                review_n = int(mrev.group(1))
            if mcol:
                collect_n = int(mcol.group(1))
            # score / points: <span itemprop="scoreCount">28,504,966</span>
            mscore = re.search(r'itemprop=\"scoreCount\"[^>]*>([^<]{1,24})<', dt)
            if mscore:
                score_n = _parse_count_text(mscore.group(1))
        except Exception:
            pass

        out.append(
            {
                "platform": "晋江",
                "title": title,
                "author": author,
                "link": f"https://www.jjwxc.net/onebook.php?novelid={novelid}",
                "type": "",
                "rank_source": "晋江-TopTen",
                "rank_pos": rank_pos,
                "heat": float(max(1, (limit - rank_pos + 1))),
                "reason": f"晋江TopTen收录，第{rank_pos}条",
                "desc": desc[:400] if desc else "",
                "finish": finish,
                "collect_num": collect_n,
                "review_num": review_n,
                "score_num": score_n,
            }
        )
        if len(out) >= int(limit or 30):
            break
    return out


def fetch_jjwxc_search(query, limit=30, order="novelscore"):
    """
    JJWXC keyword search API (no JS rendering needed):
      https://www.jjwxc.net/search/search_ajax.php?action=search&keywords=...&type=1&version=1&getfull=1
    `type=1` means search by work title.

    order:
      - "novelscore": points / score (default)
      - "collect": collected count (client-side sort; we still fetch details per novel)
    """
    query = _clean_ws(query)
    if not query:
        return []
    limit = int(limit or 30)

    url = "https://www.jjwxc.net/search/search_ajax.php"
    params = {"action": "search", "keywords": query, "type": 1, "version": 1, "getfull": 1}
    resp = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=20)
    data = {}
    try:
        data = resp.json() or {}
    except Exception:
        return []
    rows = data.get("data") or []
    out = []

    # Fetch detail for each novelid (GBK page).
    for row in rows:
        if len(out) >= limit:
            break
        try:
            novelid = int(row.get("novelid") or 0)
        except Exception:
            novelid = 0
        if not novelid:
            continue
        title = _clean_ws(row.get("novelname")).strip("《》")
        author = _clean_ws(row.get("authorname"))
        if not title:
            continue

        desc = ""
        finish = "未知"
        collect_n = None
        review_n = None
        score_n = None
        try:
            d = requests.get(
                f"https://www.jjwxc.net/onebook.php?novelid={novelid}",
                headers={"User-Agent": UA},
                timeout=20,
            )
            d.encoding = "gbk"
            dt = d.text
            mdesc = re.search(r'id=\"novelintro\"[^>]*>(.*?)</div>', dt, flags=re.S)
            if mdesc:
                raw = mdesc.group(1)
                raw = re.sub(r"<img[^>]*>", " ", raw)
                raw = re.sub(r"<br\\s*/?>", "\n", raw, flags=re.I)
                raw = re.sub(r"<[^>]+>", " ", raw)
                desc = _clean_ws(unescape(raw))
            mfin = re.search(r'itemprop=\"updataStatus\"[^>]*>\s*<font[^>]*>([^<]{1,10})<', dt, flags=re.S)
            if mfin and "完结" in mfin.group(1):
                finish = "完结"
            elif mfin:
                finish = "连载"
            mrev = re.search(r'itemprop=\"reviewCount\"[^>]*>(\d{1,12})<', dt)
            mcol = re.search(r'itemprop=\"collectedCount\"[^>]*>(\d{1,12})<', dt)
            if mrev:
                review_n = int(mrev.group(1))
            if mcol:
                collect_n = int(mcol.group(1))
            mscore = re.search(r'itemprop=\"scoreCount\"[^>]*>([^<]{1,24})<', dt)
            if mscore:
                score_n = _parse_count_text(mscore.group(1))
        except Exception:
            pass

        # Heat: use available numbers for a stable sorting signal.
        heat = 1.0
        if isinstance(score_n, int) and score_n > 0:
            heat = float(score_n)
        elif isinstance(collect_n, int) and collect_n > 0:
            heat = float(collect_n)
        elif isinstance(review_n, int) and review_n > 0:
            heat = float(review_n)

        out.append(
            {
                "platform": "晋江",
                "title": title,
                "author": author,
                "link": f"https://www.jjwxc.net/onebook.php?novelid={novelid}",
                "type": query,  # store keyword for filtering/sorting
                "rank_source": f"晋江-关键词搜索:{query}",
                "rank_pos": len(out) + 1,
                "heat": heat,
                "reason": f"晋江关键词搜索命中：{query}",
                "desc": desc[:400] if desc else "",
                "finish": finish,
                "collect_num": collect_n,
                "review_num": review_n,
                "score_num": score_n,
            }
        )

    if order == "collect":
        out.sort(key=lambda x: (x.get("collect_num") or 0, x.get("score_num") or 0, x.get("heat") or 0), reverse=True)
        for i, it in enumerate(out, 1):
            it["rank_pos"] = i
    return out[:limit]


def fetch_fanqie_rank_filtered(query, limit=30, max_pool=160):
    """
    Fanqie keyword search API is hard to call reliably (frontend signing). Practical fallback:
      1) collect a pool of candidate /page/<id> from rank pages
      2) fetch detail pages one-by-one, stop early once we have enough keyword hits
    """
    query = _clean_ws(query)
    if not query:
        return []
    limit = int(limit or 30)
    max_pool = int(max_pool or 260)
    q = query.lower()

    # Collect candidate ids (same logic as fetch_fanqie_rank but without fetching all details).
    entry_url = "https://fanqienovel.com/rank"
    entry_html = requests.get(entry_url, headers={"User-Agent": UA}, timeout=20).text
    rank_paths = ["/rank"]
    # Keep runtime bounded; this is a fallback, not an exhaustive search.
    more = sorted(set(re.findall(r'href=\"(/rank/[0-9_]+)\"', entry_html)))[:12]
    rank_paths.extend(more)

    seen = set()
    page_ids = []
    page_meta = {}  # pid -> rank_source
    page_stats = {}  # pid -> {"inread_text": str, "inread_num": int|None}
    for path in rank_paths:
        if len(page_ids) >= max_pool:
            break
        url = f"https://fanqienovel.com{path}" if path != "/rank" else entry_url
        try:
            html = requests.get(url, headers={"User-Agent": UA}, timeout=20).text
        except Exception:
            continue
        blocks = re.split(r'<div class=\"rank-book-item\">', html)
        for b in blocks[1:]:
            m = re.search(r'href=\"/page/(\d+)\"', b)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            page_ids.append(pid)
            page_meta[pid] = f"番茄小说-{path}"
            m2 = re.search(r'在读：<!-- -->\s*([^<]{1,20})<', b)
            inread_text = _clean_ws(m2.group(1)) if m2 else ""
            inread_num = _parse_count_text(inread_text) if inread_text else None
            if inread_text:
                page_stats[pid] = {"inread_text": inread_text, "inread_num": inread_num}
            if len(page_ids) >= max_pool:
                break

    out = []
    for pid in page_ids:
        if len(out) >= limit:
            break
        url = f"https://fanqienovel.com/page/{pid}"
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            text = resp.text
        except Exception:
            continue

        m = re.search(r"<title>(.*?)</title>", text, flags=re.S)
        title_tag = _clean_ws(unescape(m.group(1)) if m else "")
        title = title_tag.split("完整版在线免费阅读", 1)[0] if title_tag else ""
        title = title.split("_", 1)[0].strip()

        # type tags
        cats = re.findall(r'<span class=\"info-label-grey\">([^<]{1,30})</span>', text)
        cats = [_clean_ws(unescape(c)) for c in cats if _clean_ws(c)]

        desc = ""
        m = re.search(r'<meta[^>]+name=\"description\"[^>]+content=\"([^\"]+)\"', text, flags=re.I)
        if m:
            desc = _clean_ws(unescape(m.group(1)))[:400]

        blob = " ".join([title, " / ".join(cats[:4]), desc]).lower()
        if q not in blob:
            continue

        # author via meta keywords (same as fetch_fanqie_rank)
        kw = ""
        m = re.search(r'<meta[^>]+name=\"keywords\"[^>]+content=\"([^\"]+)\"', text, flags=re.I)
        if m:
            kw = _clean_ws(unescape(m.group(1)))
        author = ""
        if kw and title:
            parts = [p.strip() for p in kw.split(",") if p.strip()]
            for p in parts:
                if p.endswith(f"小说{title}") and len(p) <= 60:
                    author = p[: -len(f"小说{title}")].strip()
                    break
            if not author:
                for p in parts:
                    m2 = re.search(rf"([^,]{{1,30}})小说{re.escape(title)}$", p)
                    if m2:
                        author = m2.group(1).strip()
                        break
        if not author:
            m3 = re.search(r"作者[:：]\s*([^<\\s]{1,30})", text)
            if m3:
                author = m3.group(1).strip()

        finish = "未知"
        if "已完结" in text:
            finish = "完结"
        elif "连载" in text:
            finish = "连载"

        st = page_stats.get(pid) or {}
        inread_text = st.get("inread_text", "")
        inread_num = st.get("inread_num", None)
        heat = float(inread_num) if isinstance(inread_num, int) and inread_num > 0 else 1.0

        out.append(
            {
                "platform": "番茄",
                "title": title or "",
                "author": author or "",
                "link": url,
                "type": " / ".join(cats[:4]) if cats else query,
                "rank_source": f"番茄-排行筛选:{query}",
                "rank_pos": len(out) + 1,
                "heat": heat,
                "reason": f"番茄排行池筛选命中关键词：{query}",
                "desc": desc,
                "finish": finish,
                "inread_text": inread_text,
                "inread_num": inread_num,
            }
        )

    return out


def upsert_prescreen(items, dry_run=False, batch=""):
    client = FeishuClient()
    if not client.is_configured():
        raise RuntimeError("飞书未配置")
    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("选题库-初筛")
    if not table_id:
        raise RuntimeError("未配置 选题库-初筛 table_id")

    field_meta = client.get_table_field_meta(table_id) or {}
    available = set(field_meta.keys())

    def _options(field_name):
        it = field_meta.get(field_name) or {}
        opts = (it.get("property") or {}).get("options") or []
        names = [str(o.get("name", "")).strip() for o in opts if str(o.get("name", "")).strip()]
        return set(names)

    platform_opts = _options("平台") if "平台" in available else set()
    report_opts = _options("上报方式") if "上报方式" in available else set()
    finish_opts = _options("是否完结") if "是否完结" in available else set()
    dims_opts = _options("入选维度") if "入选维度" in available else set()

    created = 0
    updated = 0
    skipped = 0
    errors = 0
    for it in items:
        title = _clean_ws(it.get("title"))
        author = _clean_ws(it.get("author"))
        platform = _clean_ws(it.get("platform"))
        if not title or not platform:
            continue
        dedupe = f"{platform}|{title}|{author}".strip("|")

        # Find existing by 去重Key if possible (so we can avoid overwriting manual fields).
        existing = None
        existing_id = None
        if "去重Key" in available:
            existing = client.find_first_record_by_fields(table_id, {"去重Key": dedupe})
            if existing:
                existing_id = existing.get("record_id")
        existing_fields = (existing or {}).get("fields", {}) or {}

        fields = {}
        if "作品名称" in available:
            fields["作品名称"] = title
        if "作者" in available:
            fields["作者"] = author
        if "平台" in available:
            # Feishu accepts option names for SingleSelect; use names to keep table readable.
            p = platform if platform in ["晋江", "番茄", "起点", "其他"] else "其他"
            if platform_opts and p not in platform_opts:
                p = "其他" if "其他" in platform_opts else (next(iter(platform_opts)) if platform_opts else p)
            fields["平台"] = p
        if "类型" in available:
            fields["类型"] = _clean_ws(it.get("type"))
        if "作品链接" in available:
            fields["作品链接"] = _clean_ws(it.get("link"))
        if "去重Key" in available:
            fields["去重Key"] = dedupe
        if "榜单来源" in available:
            fields["榜单来源"] = _clean_ws(it.get("rank_source"))
        if "榜单排名" in available:
            fields["榜单排名"] = float(it.get("rank_pos") or 0)
        if "推荐热度" in available:
            # keep legacy numeric if present
            fields["推荐热度"] = float(it.get("heat") or 0)
        if "推荐热度_数值" in available:
            fields["推荐热度_数值"] = float(it.get("heat") or 0)
        if "在读量" in available:
            v = it.get("inread_text") or ""
            if v:
                fields["在读量"] = str(v)
        if "在读量_数值" in available:
            v = it.get("inread_num")
            if isinstance(v, int):
                fields["在读量_数值"] = float(v)
        if "推荐理由" in available:
            fields["推荐理由"] = _clean_ws(it.get("reason"))
        if "简介" in available:
            fields["简介"] = _clean_ws(it.get("desc"))[:400]
        if "是否完结" in available:
            fin = str(it.get("finish") or "未知").strip()
            if fin not in ["完结", "连载", "未知"]:
                fin = "未知"
            if finish_opts and fin not in finish_opts:
                fin = "未知" if "未知" in finish_opts else (next(iter(finish_opts)) if finish_opts else fin)
            fields["是否完结"] = fin
        if "平台评分_数值" in available:
            v = it.get("score_num")
            if isinstance(v, int):
                fields["平台评分_数值"] = float(v)
        if "收藏量_数值" in available:
            v = it.get("collect_num")
            if isinstance(v, int):
                fields["收藏量_数值"] = float(v)
                if "收藏量" in available and not str(fields.get("收藏量", "")).strip():
                    fields["收藏量"] = str(v)
        if "书评量_数值" in available:
            v = it.get("review_num")
            if isinstance(v, int):
                fields["书评量_数值"] = float(v)
                if "书评量" in available and not str(fields.get("书评量", "")).strip():
                    fields["书评量"] = str(v)
        if "提取状态" in available:
            fields["提取状态"] = "成功"
        if "上报方式" in available:
            r = "系统抓取"
            if report_opts and r not in report_opts:
                r = next(iter(report_opts)) if report_opts else r
            fields["上报方式"] = r
        if "添加时间" in available:
            fields["添加时间"] = _now_ms()
        if "最近更新" in available:
            fields["最近更新"] = _now_ms()
        if "抓取批次" in available:
            fields["抓取批次"] = batch or datetime.now().strftime("%Y-%m-%d")

        # Default dimensions: mark high heat since this is ranking-based.
        if "入选维度" in available:
            cur_dims = it.get("dims") or []
            if not isinstance(cur_dims, list):
                cur_dims = [str(cur_dims)]
            cur_dims = [str(x).strip() for x in cur_dims if str(x).strip()]
            if not cur_dims:
                cur_dims = ["高热度"] if float(it.get("heat") or 0) > 0 else ["待人工判断"]
            # Clamp to known options if possible, to avoid creating option names accidentally.
            if dims_opts:
                cur_dims = [d for d in cur_dims if d in dims_opts]
            fields["入选维度"] = cur_dims or (["高热度"] if (not dims_opts or "高热度" in dims_opts) else list(dims_opts)[:1])

        # Default 是否入库 only when empty; never overwrite manual selection.
        if "是否入库" in available and not str(existing_fields.get("是否入库", "")).strip():
            fields["是否入库"] = "否"

        fields = client.filter_fields(table_id, fields)

        try:
            rid = existing_id
            if rid:
                if dry_run:
                    skipped += 1
                    append_jsonl(
                        os.path.join(PATHS["logs"], "prescreen_ingest_dryrun.jsonl"),
                        {"ts": now_ts(), "action": "would_update", "record_id": rid, "fields": fields},
                    )
                else:
                    client.update_record_in_table(table_id, rid, fields)
                    updated += 1
                    append_jsonl(
                        os.path.join(PATHS["logs"], "prescreen_ingest.jsonl"),
                        {"ts": now_ts(), "action": "updated", "record_id": rid, "fields": fields},
                    )
            else:
                if dry_run:
                    append_jsonl(
                        os.path.join(PATHS["logs"], "prescreen_ingest_dryrun.jsonl"),
                        {"ts": now_ts(), "action": "would_create", "dedupe": dedupe, "fields": fields},
                    )
                    created += 1
                else:
                    rid2 = client.create_record_in_table(table_id, fields)
                    created += 1
                    append_jsonl(
                        os.path.join(PATHS["logs"], "prescreen_ingest.jsonl"),
                        {"ts": now_ts(), "action": "created", "record_id": rid2, "fields": fields},
                    )
        except Exception as e:
            errors += 1
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_ingest_errors.jsonl"),
                {"ts": now_ts(), "error": str(e), "title": title, "author": author, "platform": platform},
            )

    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="fanqie,jjwxc", help="fanqie,jjwxc,qidian(best-effort)")
    parser.add_argument("--mode", default="rank", choices=["rank", "search"], help="rank: pull platform ranking; search: keyword/type search")
    parser.add_argument("--query", default="", help="keyword/type for mode=search (e.g. 末世/种田)")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch", default="")
    parser.add_argument("--audit", action="store_true", help="print per-field fill rate for fetched items")
    args = parser.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    ensure_dirs()

    sources = [x.strip().lower() for x in (args.sources or "").split(",") if x.strip()]
    items = []
    if args.mode == "search":
        q = _clean_ws(args.query)
        if "fanqie" in sources and q:
            items.extend(fetch_fanqie_rank_filtered(query=q, limit=args.limit))
        if "jjwxc" in sources and q:
            items.extend(fetch_jjwxc_search(query=q, limit=min(args.limit, 30)))
    else:
        if "fanqie" in sources:
            items.extend(fetch_fanqie_rank(limit=args.limit))
        if "jjwxc" in sources:
            items.extend(fetch_jjwxc_topten(limit=min(args.limit, 30)))

    if args.audit:
        keys = [
            "platform",
            "title",
            "author",
            "link",
            "type",
            "rank_source",
            "rank_pos",
            "heat",
            "desc",
            "finish",
            "inread_text",
            "inread_num",
            "collect_num",
            "review_num",
            "score_num",
        ]
        stats = {k: 0 for k in keys}
        for it in items:
            for k in keys:
                v = it.get(k)
                ok = False
                if v is None:
                    ok = False
                elif isinstance(v, str):
                    ok = bool(v.strip())
                elif isinstance(v, (int, float)):
                    ok = True
                else:
                    ok = True
                if ok:
                    stats[k] += 1
        total = len(items) or 1
        print("AUDIT fill rate:")
        for k in keys:
            print(f"- {k}: {stats[k]}/{len(items)} ({int(round(stats[k]*100/total))}%)")

    res = upsert_prescreen(items, dry_run=args.dry_run, batch=args.batch)
    print(json.dumps({"fetched": len(items), **res, "dry_run": bool(args.dry_run)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
