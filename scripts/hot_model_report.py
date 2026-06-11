import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs
from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.utils import append_jsonl, read_jsonl


def to_float(v):
    try:
        if v is None:
            return 0.0
        s = str(v).strip()
        if not s:
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def parse_dt(v):
    if isinstance(v, (int, float)):
        x = float(v)
        # Support epoch seconds or milliseconds.
        if x > 100000000000:
            x = x / 1000.0
        try:
            return datetime.fromtimestamp(x)
        except Exception:
            return None
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ["%Y年%m月%d日%H时%M分%S秒", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def normalize_from_feishu(items):
    out = []
    for it in items:
        f = it.get("fields") or {}
        title = str(f.get("笔记标题", "")).strip()
        if not title:
            continue
        dt = parse_dt(f.get("首次发布时间"))
        exposure = to_float(f.get("曝光"))
        views = to_float(f.get("观看量"))
        likes = to_float(f.get("点赞"))
        comments = to_float(f.get("评论"))
        favs = to_float(f.get("收藏"))
        shares = to_float(f.get("分享"))
        fans = to_float(f.get("涨粉"))
        score = to_float(f.get("爆款分"))
        out.append(
            {
                "title": title,
                "note_uid": str(f.get("笔记唯一键", "")).strip(),
                "experiment_id": str(f.get("实验ID", "")).strip(),
                "experiment_version": str(f.get("实验版本", "")).strip(),
                "experiment_variable": str(f.get("实验变量", "")).strip(),
                "dt": dt,
                "genre": str(f.get("体裁", "")).strip() or "未知",
                "recovery_tag": str(f.get("恢复期标签", "")).strip() or "未知",
                "exposure": exposure,
                "views": views,
                "likes": likes,
                "comments": comments,
                "favs": favs,
                "shares": shares,
                "fans": fans,
                "score": score,
                "inter_rate_exp": to_float(f.get("互动率_按曝光")),
                "fav_rate_view": to_float(f.get("收藏率_按观看")),
                "comment_rate_view": to_float(f.get("评论率_按观看")),
                "share_rate_view": to_float(f.get("分享率_按观看")),
                "fan_rate_exp": to_float(f.get("涨粉率_按曝光")),
            }
        )
    return out


def normalize_from_local(path):
    out = []
    for it in read_jsonl(path):
        title = str(it.get("笔记标题", "")).strip()
        if not title:
            continue
        dt = parse_dt(it.get("首次发布时间"))
        out.append(
            {
                "title": title,
                "note_uid": str(it.get("笔记唯一键", "")).strip(),
                "experiment_id": str(it.get("实验ID", "")).strip(),
                "experiment_version": str(it.get("实验版本", "")).strip(),
                "experiment_variable": str(it.get("实验变量", "")).strip(),
                "dt": dt,
                "genre": str(it.get("体裁", "")).strip() or "未知",
                "recovery_tag": str(it.get("恢复期标签", "")).strip() or "未知",
                "exposure": to_float(it.get("曝光")),
                "views": to_float(it.get("观看量")),
                "likes": to_float(it.get("点赞")),
                "comments": to_float(it.get("评论")),
                "favs": to_float(it.get("收藏")),
                "shares": to_float(it.get("分享")),
                "fans": to_float(it.get("涨粉")),
                "score": to_float(it.get("爆款分")),
                "inter_rate_exp": to_float(it.get("互动率_按曝光")),
                "fav_rate_view": to_float(it.get("收藏率_按观看")),
                "comment_rate_view": to_float(it.get("评论率_按观看")),
                "share_rate_view": to_float(it.get("分享率_按观看")),
                "fan_rate_exp": to_float(it.get("涨粉率_按曝光")),
            }
        )
    return out


def avg(rows, key):
    vals = [to_float(x.get(key)) for x in rows]
    return sum(vals) / len(vals) if vals else 0.0


def analyze(rows, min_exposure=30):
    if not rows:
        return {"summary": {}, "top_notes": [], "factors": []}
    model_rows = [x for x in rows if x.get("exposure", 0) >= float(min_exposure)]
    if not model_rows:
        model_rows = list(rows)
    total = len(rows)
    exp_sum = sum(x["exposure"] for x in rows)
    view_sum = sum(x["views"] for x in rows)
    inter_sum = sum(x["likes"] + x["comments"] + x["favs"] + x["shares"] for x in rows)
    fans_sum = sum(x["fans"] for x in rows)
    summary = {
        "样本数": total,
        "建模样本数(曝光过滤后)": len(model_rows),
        "建模最小曝光阈值": float(min_exposure),
        "总曝光": exp_sum,
        "总观看": view_sum,
        "总互动": inter_sum,
        "总涨粉": fans_sum,
        "观看率(观看/曝光)": (view_sum / exp_sum) if exp_sum > 0 else 0.0,
        "互动率(互动/曝光)": (inter_sum / exp_sum) if exp_sum > 0 else 0.0,
        "均值爆款分": avg(rows, "score"),
    }

    top_notes = sorted(model_rows, key=lambda x: (x["score"], x["favs"], x["views"]), reverse=True)[:5]

    groups = defaultdict(list)
    for x in model_rows:
        groups[f"恢复期={x['recovery_tag']}"].append(x)
        groups[f"体裁={x['genre']}"].append(x)
        hour = x["dt"].hour if x.get("dt") else -1
        slot = "未知"
        if 6 <= hour < 12:
            slot = "早间"
        elif 12 <= hour < 18:
            slot = "下午"
        elif 18 <= hour < 24:
            slot = "晚间"
        elif 0 <= hour < 6:
            slot = "凌晨"
        groups[f"发布时间段={slot}"].append(x)

    factors = []
    base_score = summary["均值爆款分"]
    for k, rs in groups.items():
        if len(rs) < 2:
            continue
        s = avg(rs, "score")
        delta = s - base_score
        factors.append(
            {
                "因子": k,
                "样本数": len(rs),
                "均值爆款分": s,
                "相对全局差值": delta,
                "收藏率(按观看)": avg(rs, "fav_rate_view"),
                "评论率(按观看)": avg(rs, "comment_rate_view"),
                "分享率(按观看)": avg(rs, "share_rate_view"),
            }
        )
    factors.sort(key=lambda x: x["相对全局差值"], reverse=True)
    return {"summary": summary, "top_notes": top_notes, "factors": factors}


def render_md(data, title, from_date, to_date):
    s = data["summary"]
    lines = [
        f"# {title}",
        "",
        f"- 时间范围: {from_date} ~ {to_date}",
        f"- 样本数: {s.get('样本数', 0)}",
        f"- 建模样本数(曝光过滤后): {s.get('建模样本数(曝光过滤后)', 0)}",
        f"- 建模最小曝光阈值: {s.get('建模最小曝光阈值', 0)}",
        "",
        "## 一、总体表现",
        f"- 总曝光: {int(s.get('总曝光', 0))}",
        f"- 总观看: {int(s.get('总观看', 0))}",
        f"- 总互动: {int(s.get('总互动', 0))}",
        f"- 总涨粉: {int(s.get('总涨粉', 0))}",
        f"- 观看率(观看/曝光): {s.get('观看率(观看/曝光)', 0)*100:.2f}%",
        f"- 互动率(互动/曝光): {s.get('互动率(互动/曝光)', 0)*100:.2f}%",
        f"- 均值爆款分: {s.get('均值爆款分', 0):.4f}",
        "",
        "## 二、Top 笔记（按爆款分）",
    ]
    for i, n in enumerate(data["top_notes"], 1):
        lines.append(
            f"{i}. {n['title']} | 曝光 {int(n['exposure'])} | 观看 {int(n['views'])} | 收藏 {int(n['favs'])} | 爆款分 {n['score']:.4f}"
        )

    lines.extend(["", "## 三、因子分析（可复用）"])
    if not data["factors"]:
        lines.append("- 样本不足，暂不输出稳定因子（建议样本>=20）。")
    else:
        for f in data["factors"][:10]:
            lines.append(
                f"- {f['因子']} | 样本 {f['样本数']} | 均值爆款分 {f['均值爆款分']:.4f} | 相对全局 {f['相对全局差值']:+.4f}"
            )

    lines.extend(
        [
            "",
            "## 四、下周 A/B 建议",
            "- 每天 1 篇，单次只改 1 个变量（标题结构 / 钩子句 / 发布时间段）。",
            "- 继续区分“恢复前/恢复后”样本，不混算。",
            "- 每周复盘时，优先看收藏率与分享率，再看曝光。",
            "",
        ]
    )
    return "\n".join(lines)


def maybe_sync_factors(factors, dry_run=False, experiment_id=""):
    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("爆款因子库")
    if not table_id:
        return {"enabled": False, "reason": "未配置 FEISHU_HOT_FACTORS_TABLE_ID"}
    c = FeishuClient()
    if not c.is_configured():
        return {"enabled": False, "reason": "飞书未配置"}
    created = 0
    updated = 0
    errors = 0
    for f in factors[:20]:
        key = str(f.get("因子", "")).strip()
        if not key:
            continue
        match_fields = {"因子名称": key}
        if experiment_id:
            match_fields["实验ID"] = experiment_id
        rec = c.find_first_record_by_fields(table_id, match_fields)
        fields = c.filter_fields(
            table_id,
            {
                "因子名称": key,
                "实验ID": experiment_id,
                "样本数": float(f.get("样本数", 0)),
                "均值爆款分": float(f.get("均值爆款分", 0)),
                "相对全局差值": float(f.get("相对全局差值", 0)),
                "收藏率（按观看）": float(f.get("收藏率(按观看)", 0)),
                "评论率（按观看）": float(f.get("评论率(按观看)", 0)),
                "分享率（按观看）": float(f.get("分享率(按观看)", 0)),
                "更新时间": int(datetime.now().timestamp() * 1000),
            },
        )
        try:
            if rec and rec.get("record_id"):
                if not dry_run:
                    c.update_record_in_table(table_id, rec["record_id"], fields)
                updated += 1
            else:
                if not dry_run:
                    c.create_record_in_table(table_id, fields)
                created += 1
        except Exception as e:
            errors += 1
            append_jsonl(
                os.path.join(PATHS["logs"], "hot_model_report_errors.jsonl"),
                {"ts": datetime.now().isoformat(timespec="seconds"), "factor": key, "error": str(e)},
            )
    return {"enabled": True, "created": created, "updated": updated, "errors": errors}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=14, help="分析近 N 天")
    p.add_argument("--min-exposure", type=float, default=30.0, help="建模时过滤低曝光样本，默认30")
    p.add_argument("--title", default="爆款基因周报")
    p.add_argument("--experiment-id", default="", help="仅统计指定实验ID样本（可选）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sync-factors", action="store_true", help="将因子摘要写入飞书爆款因子库")
    args = p.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    ensure_dirs()

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=max(1, args.days))

    rows = []
    source = "local"
    try:
        c = FeishuClient()
        cfg = get_feishu_config()
        table_id = (cfg.get("related_table_ids") or {}).get("笔记结果库")
        if c.is_configured() and table_id:
            items = list(c.iter_records(table_id, page_size=200))
            rows = normalize_from_feishu(items)
            source = "feishu"
    except Exception:
        rows = []
    if not rows:
        rows = normalize_from_local(os.path.join(PATHS["logs"], "note_metrics_records.jsonl"))
        source = "local"

    rows = [x for x in rows if x.get("dt") and start_dt <= x["dt"] <= end_dt]
    exp_id = (args.experiment_id or "").strip()
    if exp_id:
        rows = [x for x in rows if str(x.get("experiment_id", "")).strip() == exp_id]
    analysis = analyze(rows, min_exposure=args.min_exposure)

    out_dir = os.path.join(PATHS["outputs"], "分析周报")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{datetime.now().strftime('%Y%m%d')}_爆款基因周报.md")
    md = render_md(analysis, args.title, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    sync_res = None
    if args.sync_factors:
        sync_res = maybe_sync_factors(analysis.get("factors") or [], dry_run=args.dry_run, experiment_id=exp_id)

    append_jsonl(
        os.path.join(PATHS["logs"], "hot_model_reports.jsonl"),
        {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "rows": len(rows),
            "experiment_id": exp_id,
            "out_path": out_path,
            "sync_factors": sync_res,
        },
    )
    print({"source": source, "rows": len(rows), "out_path": out_path, "sync_factors": sync_res})


if __name__ == "__main__":
    main()
