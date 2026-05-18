# Problem Solution Board

問題と対策を登録・検索・論理削除できる、Flask + SQLite の小さいWebアプリです。デザインは Stack Overflow 風です。検索は Elasticsearch などを使わず、Python の `re` による grep 風の正規表現検索です。文明が過剰設計に向かう前に、素朴な刃物で止めます。

## 機能

- 問題と対策の登録
  - 問題: `problem_title`
  - 対策: `solution_body`
  - タグ: `tags`
- 検索
  - `problem_title` と `solution_body` を対象に正規表現検索
  - タグ完全一致検索
  - 削除済みの表示切り替え
- 削除
  - 物理削除ではなく `deleted_at` に日時を入れる論理削除
- 復元
  - 削除済み表示時に復元可能

## テーブル定義

```sql
CREATE TABLE problem_solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_title TEXT NOT NULL,
    solution_body TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
```

## Dockerで起動

```bash
docker compose up --build
```

ブラウザで開きます。

```text
http://localhost:19743
```

## 公開ポートを変える

ホスト側の公開ポートを変える場合は `HOST_PORT` を指定します。

```bash
HOST_PORT=18080 docker compose up --build
```

この場合は次で開きます。

```text
http://localhost:18080
```

コンテナ内部のポートも変えたい場合は `PORT` も指定します。

```bash
HOST_PORT=18080 PORT=18080 docker compose up --build
```

## データ永続化

SQLiteファイルはホスト側の `./data` に保存されます。

```text
./data/app.sqlite3
```

## ローカルで直接起動

Dockerを使わない場合です。まあDocker要件なのにローカル起動も書く、こういう余計な親切がREADMEを太らせます。

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

デフォルトでは `http://localhost:19743` で起動します。

## 正規表現検索の例

```text
timeout|permission|権限
```

```text
cron.*多重|flock
```

検索は `re.IGNORECASE | re.MULTILINE` で行います。不正な正規表現を入力した場合は一致なしとして扱います。

## ファイル構成

```text
.
├── app.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── README.md
├── static
│   └── style.css
└── templates
    ├── base.html
    ├── form.html
    └── index.html
```

## 環境変数

| 変数 | デフォルト | 説明 |
|---|---:|---|
| `PORT` | `19743` | Flask/Gunicornがlistenするコンテナ内ポート |
| `HOST_PORT` | `19743` | docker composeで公開するホスト側ポート |
| `SECRET_KEY` | `change-me` | Flaskのセッション用秘密鍵 |
| `DATA_DIR` | `/app/data` | SQLite保存ディレクトリ |
| `WORKERS` | `2` | Gunicorn worker数 |

## 注意

このアプリは小規模な個人用・内部用を想定しています。タグは正規化してカンマ区切りで保存しています。巨大データを扱うなら検索のたびに全件をPython側でなめる設計は当然遅くなります。grep風検索という要件なので、そこは仕様です。仕様という名の免罪符、便利ですね。

## Markdown / コードハイライト

対策本文はMarkdownとして表示されます。コードフェンスは言語名を付けるとPygmentsでハイライトされます。

````markdown
## Pythonでの対策

```py
from pathlib import Path

print(Path.cwd())
```

- 箇条書き
- **太字**
- | table | ok |
  |---|---|
  | a | b |
````

生HTMLはXSSを避けるためサニタイズします。Markdownビューアなのに攻撃面まで広げるのは、さすがに文明の敗北なので。
