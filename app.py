import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import bleach
import markdown
from flask import Flask, flash, g, redirect, render_template, request, url_for
from markupsafe import Markup

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("DATABASE_PATH", DATA_DIR / "app.sqlite3"))

MARKDOWN_EXTENSIONS = [
    "extra",                       # tables, attr_list, definition lists, etc.
    "fenced_code",                 # ```py style code fences
    "codehilite",                  # Pygments syntax highlighting
    "nl2br",                       # line breaks behave closer to GitHub/Stack Overflow input
    "sane_lists",
    "pymdownx.superfences",        # better fenced code blocks
    "pymdownx.inlinehilite",
    "pymdownx.highlight",
    "pymdownx.tasklist",
    "pymdownx.tilde",              # ~~strikethrough~~
    "pymdownx.mark",
]

MARKDOWN_EXTENSION_CONFIGS = {
    "codehilite": {
        "guess_lang": False,
        "linenums": False,
        "css_class": "codehilite",
    },
    "pymdownx.highlight": {
        "guess_lang": False,
        "use_pygments": True,
        "pygments_lang_class": True,
        "css_class": "codehilite",
    },
    "pymdownx.tasklist": {
        "custom_checkbox": True,
    },
}

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union({
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "pre", "code", "span", "div",
    "table", "thead", "tbody", "tr", "th", "td",
    "ul", "ol", "li",
    "blockquote",
    "strong", "em", "del", "mark",
    "input",
})

ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "title"],
    "a": ["href", "title", "rel", "target"],
    "code": ["class"],
    "pre": ["class"],
    "span": ["class"],
    "div": ["class"],
    "table": ["class"],
    "th": ["align"],
    "td": ["align"],
    "input": ["type", "checked", "disabled"],
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    app.config["DATABASE"] = str(DB_PATH)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    @app.before_request
    def before_request() -> None:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row

    @app.teardown_request
    def teardown_request(exception: Exception | None) -> None:
        db = getattr(g, "db", None)
        if db is not None:
            db.close()

    @app.template_filter("markdown")
    def markdown_filter(text: str | None) -> Markup:
        return render_markdown(text or "")

    init_db(app.config["DATABASE"])

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()
        tag = request.args.get("tag", "").strip()
        include_deleted = request.args.get("include_deleted") == "1"
        rows = search_records(g.db, query=query, tag=tag, include_deleted=include_deleted)
        return render_template(
            "index.html",
            rows=rows,
            query=query,
            tag=tag,
            include_deleted=include_deleted,
        )

    @app.route("/new", methods=["GET", "POST"])
    def new_record():
        if request.method == "POST":
            problem_title = request.form.get("problem_title", "").strip()
            solution_body = request.form.get("solution_body", "").strip()
            tags = normalize_tags(request.form.get("tags", ""))

            errors = validate_record(problem_title, solution_body)
            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template(
                    "form.html",
                    record={
                        "problem_title": problem_title,
                        "solution_body": solution_body,
                        "tags": tags,
                    },
                ), 400

            ts = now_text()
            g.db.execute(
                """
                INSERT INTO problem_solutions
                    (problem_title, solution_body, tags, created_at, updated_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (problem_title, solution_body, tags, ts, ts),
            )
            g.db.commit()
            flash("登録しました。Markdownもコードも飲み込む、メモ帳の上位互換です。", "success")
            return redirect(url_for("index"))

        return render_template("form.html", record={})

    @app.post("/delete/<int:record_id>")
    def delete_record(record_id: int):
        ts = now_text()
        cur = g.db.execute(
            """
            UPDATE problem_solutions
               SET deleted_at = ?, updated_at = ?
             WHERE id = ? AND deleted_at IS NULL
            """,
            (ts, ts, record_id),
        )
        g.db.commit()
        if cur.rowcount == 0:
            flash("対象が見つからないか、すでに削除済みです。", "error")
        else:
            flash("削除しました。物理削除ではないので、DB界のゾンビです。", "success")
        return redirect(url_for("index"))

    @app.post("/restore/<int:record_id>")
    def restore_record(record_id: int):
        ts = now_text()
        cur = g.db.execute(
            """
            UPDATE problem_solutions
               SET deleted_at = NULL, updated_at = ?
             WHERE id = ? AND deleted_at IS NOT NULL
            """,
            (ts, record_id),
        )
        g.db.commit()
        if cur.rowcount == 0:
            flash("復元対象が見つからないか、削除されていません。", "error")
        else:
            flash("復元しました。ゾンビが社会復帰しました。", "success")
        return redirect(url_for("index", include_deleted=1))

    return app


def render_markdown(text: str) -> Markup:
    html = markdown.markdown(
        text,
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs=MARKDOWN_EXTENSION_CONFIGS,
        output_format="html5",
    )
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    linked = bleach.linkify(cleaned, callbacks=[set_link_attrs])
    return Markup(linked)


def set_link_attrs(attrs: dict[str, str], new: bool = False) -> dict[str, str]:
    attrs[(None, "rel")] = "nofollow noopener noreferrer"
    attrs[(None, "target")] = "_blank"
    return attrs


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS problem_solutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_title TEXT NOT NULL,
                solution_body TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_problem_solutions_deleted_at ON problem_solutions(deleted_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_problem_solutions_created_at ON problem_solutions(created_at)")
        db.commit()


def validate_record(problem_title: str, solution_body: str) -> list[str]:
    errors = []
    if not problem_title:
        errors.append("問題タイトルは必須です。")
    if not solution_body:
        errors.append("対策本文は必須です。")
    if len(problem_title) > 300:
        errors.append("問題タイトルは300文字以内にしてください。")
    return errors


def normalize_tags(raw_tags: str) -> str:
    parts = []
    for tag in re.split(r"[,，\s]+", raw_tags.strip()):
        tag = tag.strip().lower()
        if tag and tag not in parts:
            parts.append(tag)
    return ",".join(parts)


def split_tags(tags: str) -> list[str]:
    return [tag for tag in tags.split(",") if tag]


def regex_match(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None
    except re.error:
        return False


def search_records(db: sqlite3.Connection, query: str = "", tag: str = "", include_deleted: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM problem_solutions"
    params: list[Any] = []
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY updated_at DESC, id DESC"

    records = [dict(row) for row in db.execute(sql, params).fetchall()]

    normalized_tag = tag.strip().lower()
    if normalized_tag:
        records = [row for row in records if normalized_tag in split_tags(row.get("tags", ""))]

    if query:
        filtered = []
        for row in records:
            target = f"{row['problem_title']}\n{row['solution_body']}"
            if regex_match(query, target):
                filtered.append(row)
        records = filtered

    for row in records:
        row["tag_list"] = split_tags(row.get("tags", ""))
    return records


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "19743"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
