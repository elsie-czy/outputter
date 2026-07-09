from flask import Blueprint, render_template

bp = Blueprint("web_landing", __name__)


@bp.get("/")
def landing():
    """未登录可访问的门户首页。"""
    return render_template("landing.html", active_page="landing")


@bp.get("/deconstruct")
def deconstruct_page():
    """拆文中心 — 三栏交互页面"""
    return render_template("deconstruct_center.html", active_page="deconstruct")


@bp.get("/notes")
def notes_page():
    """笔记生成 — V2.0（占位）"""
    return render_template("landing.html", active_page="notes")
