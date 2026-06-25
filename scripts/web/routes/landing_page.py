from flask import Blueprint, redirect, render_template, url_for

bp = Blueprint("web_landing", __name__)


@bp.get("/")
def landing():
    """默认跳转至运营工作台（数据总览）"""
    return redirect(url_for("web_dashboard.dashboard_page"))


@bp.get("/deconstruct")
def deconstruct_page():
    """拆文中心 — 三栏交互页面"""
    return render_template("deconstruct_center.html", active_page="deconstruct")


@bp.get("/notes")
def notes_page():
    """笔记生成 — V2.0（占位）"""
    return render_template("landing.html", active_page="notes")
