"""Render the practice guide (Markdown for the archive, HTML for phones and PCs).

All text comes from the model and, through it, from web pages: everything is escaped,
and only http(s) URLs become links.
"""
from __future__ import annotations

import datetime as dt
from html import escape

CORNER_NAMES = {"news": "最新AIニュース", "practice": "エンジニアの実践ノウハウ", "creative": "クリエイティブAI"}
WEEK = "月火水木金土日"


def _date_ja(date: str) -> str:
    d = dt.date.fromisoformat(date)
    return f"{d.year}年{d.month}月{d.day}日（{WEEK[d.weekday()]}）"


def _safe_url(u: str) -> str | None:
    return u if isinstance(u, str) and u.startswith(("https://", "http://")) else None


def _pub(n: dict) -> str:
    pub = (n.get("published") or "")[:16].replace("T", " ")
    upd = (n.get("updated") or "")[:16].replace("T", " ")
    s = f"{n.get('publisher', '')}・公開 {pub}"
    if upd and upd != pub:
        s += f"（更新 {upd}）"
    if n.get("is_backfill"):
        s += "・過去の重要情報"
    return s


def _total(n: dict) -> int:
    return int(sum(v for v in (n.get("scores") or {}).values() if isinstance(v, (int, float))))


# ---------------- Markdown ----------------

def _md_task(t: dict, title: str) -> list[str]:
    out = [f"#### {title}：{t['name']}", "", f"- **目的**：{t['goal']}", f"- **使用ツール**：{'、'.join(t['tools'])}"]
    if t.get("prep"):
        out.append(f"- **必要な準備**：{'、'.join(t['prep'])}")
    out += [f"- **所要時間**：約{t['minutes']}分", f"- **費用**：{t['cost']}"]
    if t.get("free_alternative"):
        out.append(f"- **無料の代替**：{t['free_alternative']}")
    out += ["", "**手順**", ""] + [f"{i}. {s}" for i, s in enumerate(t["steps"], 1)] + [""]
    snip = t.get("snippet")
    if snip and snip.get("type") != "removed" and snip.get("text"):
        lang = "bash" if snip["type"] == "command" else ""
        out += [f"**コピーして使う{'プロンプト' if snip['type'] == 'prompt' else 'コマンド'}**", "", f"```{lang}", snip["text"], "```"]
        if snip.get("source_url"):
            out.append(f"（出典：{snip['source_url']}）")
        out.append("")
    out += [f"- **完成するもの**：{t['deliverable']}", f"- **確認方法**：{t['success_check']}"]
    out += [f"- 参考：{u}" for u in t.get("refs", [])]
    return out + [""]


def markdown(d: dict) -> str:
    ex = d["experiment"]
    out = [f"# {d['title']}", "", f"{_date_ja(d['date'])}　AI Discovery & Build Radio 実践ガイド", "", f"> {d['overview']}", ""]
    out += ["## 今日の実験", "", f"関連ニュース：{d['news'][ex['news_index']]['headline']}", ""] + _md_task(ex, "実験")
    for i, n in enumerate(d["news"], 1):
        out += [f"## {i}. {n['headline']}", "", f"*{CORNER_NAMES.get(n['corner'], '')}｜{_pub(n)}｜評価 {_total(n)}/100*", "",
                f"出典：{n['url']}", "", f"**結論**：{n['summary']}", ""]
        if n.get("use_idea"):
            out += [f"> 💡 **こう使うと面白い**：{n['use_idea']}", ""]
        out += ["### 重要ポイント", ""]
        out += [f"- **{p}**：{dd}" if dd else f"- **{p}**" for p, dd in zip(n["points"], n["details"])]
        out += ["", "### 技術解説", "", f"**何が新しいのか**：{n['whats_new']}", "", f"**なぜ重要か**：{n['why_important']}", "",
                f"**従来との違い**：{n['difference']}", ""] + [f"- {t}" for t in n["technical_points"]]
        out += ["", "### 実践アイデア", ""] + [f"- {a}" for a in n["applications"]] + [""]
        out += _md_task(n["quick_try"], "今日すぐできること")
        b = n["build_idea"]
        out += [f"#### 発展：{b['title']}（{b['time']}）", "", b["description"], ""] + [f"{k}. {s}" for k, s in enumerate(b["steps"], 1)] + [""]
        out += ["### 利用条件・料金", "", n["terms"], "", f"**実践可能性**：{n['feasibility']}　**信頼性**：{n['reliability']}", ""]
    out += ["---", "", "この内容は公開情報をもとに AI が作成しました。手順やコマンドは出典で確認してから実行してください。", ""]
    return "\n".join(out)


# ---------------- HTML ----------------

CSS = """
:root{--bg:#f7f7f4;--fg:#1d1f24;--muted:#5d6370;--card:#fff;--line:#e3e3dd;--accent:#e2365b;--accent2:#0f8f8a;--code:#f0f0ea}
@media (prefers-color-scheme:dark){:root{--bg:#12141b;--fg:#e9eaee;--muted:#a2a7b4;--card:#1b1e28;--line:#2c303d;--accent:#ff6b8a;--accent2:#3fe0dc;--code:#0d0f15}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.8 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:820px;margin:0 auto;padding:16px 16px 64px}
a{color:var(--accent2);word-break:break-all}
header.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);margin:0 -16px 16px;padding:10px 16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--fg);text-decoration:none;font-size:14px;cursor:pointer}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
h1{font-size:1.6rem;line-height:1.4;margin:.4em 0}h2{font-size:1.3rem;margin:0 0 .4em;line-height:1.45}h3{font-size:1.05rem;margin:1.2em 0 .3em}h4{margin:1em 0 .3em}
.date{color:var(--muted);font-size:14px}.lead{font-size:1.05rem;border-left:4px solid var(--accent);padding:.2em .8em;margin:1em 0}
nav.toc ol{padding-left:1.4em;margin:.4em 0}nav.toc li{margin:.2em 0}
section.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:18px 0}
section.exp{border:2px solid var(--accent)}
.meta{color:var(--muted);font-size:13px}.badge{display:inline-block;font-size:12px;padding:1px 10px;border-radius:999px;background:var(--accent2);color:#fff;margin-right:6px}
.exp .badge{background:var(--accent)}
.task{background:var(--bg);border-radius:10px;padding:12px 14px;margin:10px 0}
dl.kv{display:grid;grid-template-columns:7.5em 1fr;gap:4px 10px;margin:.4em 0}dl.kv dt{color:var(--muted);font-size:14px}dl.kv dd{margin:0}
@media (max-width:520px){dl.kv{grid-template-columns:1fr}dl.kv dt{margin-top:6px}}
pre{background:var(--code);border:1px solid var(--line);border-radius:10px;padding:12px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;font-size:14px;margin:0}
.snip{position:relative;margin:10px 0}.copy{position:absolute;top:6px;right:6px;font-size:12px;padding:4px 10px}
ul.pts li{margin:.3em 0}.score{font-weight:700;color:var(--accent)}
.concl{font-size:1.05rem;margin:.8em 0}.idea{background:var(--bg);border-left:4px solid var(--accent2);border-radius:8px;padding:10px 14px;margin:10px 0}
details{margin:.6em 0}summary{cursor:pointer;color:var(--accent2)}
footer{color:var(--muted);font-size:13px;margin-top:32px}
"""

JS = """
document.addEventListener('click',async e=>{const b=e.target.closest('.copy');if(!b)return;
const t=b.parentNode.querySelector('pre').innerText;try{await navigator.clipboard.writeText(t);b.textContent='コピーしました';}
catch{b.textContent='選択してコピーしてください';}setTimeout(()=>b.textContent='コピー',1600);});
"""


def _a(url: str, label: str | None = None) -> str:
    u = _safe_url(url)
    if not u:
        return escape(str(url or ""))
    return f'<a href="{escape(u)}" target="_blank" rel="noopener noreferrer">{escape(label or u)}</a>'


def _snip(text: str) -> str:
    return f'<div class="snip"><button class="btn copy" type="button">コピー</button><pre>{escape(text)}</pre></div>'


def _task_html(t: dict, title: str) -> str:
    rows = [("目的", escape(t["goal"])), ("使用ツール", escape("、".join(t["tools"])))]
    if t.get("prep"):
        rows.append(("必要な準備", escape("、".join(t["prep"]))))
    rows += [("所要時間", f"約{escape(str(t['minutes']))}分"), ("費用", escape(t["cost"]))]
    if t.get("free_alternative"):
        rows.append(("無料の代替", escape(t["free_alternative"])))
    h = [f'<div class="task"><h4>{escape(title)}：{escape(t["name"])}</h4><dl class="kv">']
    h += [f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows] + ["</dl><b>手順</b><ol>"]
    h += [f"<li>{escape(s)}</li>" for s in t["steps"]] + ["</ol>"]
    snip = t.get("snippet")
    if snip and snip.get("type") != "removed" and snip.get("text"):
        h.append(f"<b>コピーして使う{'プロンプト' if snip['type'] == 'prompt' else 'コマンド'}</b>{_snip(snip['text'])}")
        if snip.get("source_url"):
            h.append(f'<div class="meta">出典：{_a(snip["source_url"])}</div>')
    h += ['<dl class="kv">', f"<dt>完成するもの</dt><dd>{escape(t['deliverable'])}</dd>",
          f"<dt>確認方法</dt><dd>{escape(t['success_check'])}</dd>", "</dl>"]
    if t.get("refs"):
        h.append('<div class="meta">参考：' + "　".join(_a(u) for u in t["refs"]) + "</div>")
    return "".join(h) + "</div>"


def _log_entry(d: dict) -> str:
    ex = d["experiment"]
    return "\n".join([f"## {d['date']} {ex['name']}", f"- 参考ニュース: {d['news'][ex['news_index']]['headline']}",
                      f"- ガイド: guides/{d['date']}.html#experiment", "- 実施日: ", "- 状況: 未着手", "- 制作物: ",
                      "- 学んだこと: ", "- 次に試したいこと: ", ""])


def html_page(d: dict, ep: dict) -> str:
    ex = d["experiment"]
    title = f"{d['title']}｜実践ガイド {d['date']}"
    minutes = int(round(ep.get("seconds", 0) / 60))
    h = ['<!doctype html><html lang="ja"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f"<title>{escape(title)}</title><style>{CSS}</style></head><body><main>",
         f'<header class="top"><a class="btn primary" href="../#{escape(d["date"])}/ja">▶ 放送を聴く</a>',
         '<a class="btn" href="#experiment">今日の実験</a><a class="btn" href="index.html">ガイド一覧</a></header>',
         f'<div class="date">{escape(_date_ja(d["date"]))}・放送 約{minutes}分</div>',
         f"<h1>{escape(d['title'])}</h1>", f'<p class="lead">{escape(d["overview"])}</p>',
         '<nav class="toc"><b>目次</b><ol><li><a href="#experiment">今日の実験：' + escape(ex["name"]) + "</a></li>"]
    h += [f'<li><a href="#news-{i}">{escape(n["headline"])}</a></li>' for i, n in enumerate(d["news"], 1)]
    h += ["</ol></nav>"]
    rel = d["news"][ex["news_index"]]
    h += ['<section class="card exp" id="experiment"><span class="badge">今日の実験</span>',
          f"<h2>{escape(ex['name'])}</h2>", f'<div class="meta">関連ニュース：<a href="#news-{ex["news_index"] + 1}">{escape(rel["headline"])}</a></div>',
          _task_html(ex, "実験"),
          "<details><summary>実践ログに記録する（非公開の private/practice-log.md に貼り付け）</summary>",
          _snip(_log_entry(d)), "</details></section>"]
    for i, n in enumerate(d["news"], 1):
        b = n["build_idea"]
        h += [f'<section class="card" id="news-{i}"><span class="badge">{escape(CORNER_NAMES.get(n["corner"], ""))}</span>',
              f'<span class="meta">評価 <span class="score">{_total(n)}</span>/100</span>',
              f"<h2>{i}. {escape(n['headline'])}</h2>", f'<div class="meta">{escape(_pub(n))}</div>',
              f'<div class="meta">出典：{_a(n["url"])}</div>',
              f'<p class="concl"><b>結論：</b>{escape(n["summary"])}</p>']
        if n.get("use_idea"):
            h.append(f'<div class="idea">💡 <b>こう使うと面白い：</b>{escape(n["use_idea"])}</div>')
        h += ["<h3>重要ポイント</h3><ul class=\"pts\">"]
        h += [f"<li><b>{escape(p)}</b>{'：' + escape(dd) if dd else ''}</li>" for p, dd in zip(n["points"], n["details"])]
        h += ["</ul><h3>技術解説</h3><dl class=\"kv\">", f"<dt>何が新しいか</dt><dd>{escape(n['whats_new'])}</dd>",
              f"<dt>なぜ重要か</dt><dd>{escape(n['why_important'])}</dd>", f"<dt>従来との違い</dt><dd>{escape(n['difference'])}</dd></dl><ul>"]
        h += [f"<li>{escape(t)}</li>" for t in n["technical_points"]] + ["</ul><h3>実践アイデア</h3><ul>"]
        h += [f"<li>{escape(a)}</li>" for a in n["applications"]] + ["</ul>", _task_html(n["quick_try"], "今日すぐできること")]
        h += [f"<h4>発展：{escape(b['title'])}（{escape(str(b['time']))}）</h4><p>{escape(b['description'])}</p><ol>"]
        h += [f"<li>{escape(s)}</li>" for s in b["steps"]] + ["</ol>"]
        h += [f"<h3>利用条件・料金</h3><p>{escape(n['terms'])}</p>",
              f'<div class="meta">実践可能性：{escape(n["feasibility"])}<br>信頼性：{escape(n["reliability"])}</div></section>']
    h += ["<footer>公開情報をもとに AI（Claude）が作成しました。手順・コマンド・料金は、必ず出典で確認してから実行してください。",
          '<br><a href="../">AI Discovery &amp; Build Radio</a></footer>', f"</main><script>{JS}</script></body></html>"]
    return "\n".join(h)


def index_page(eps: list[dict]) -> str:
    items = []
    for e in eps:
        t = (e.get("ja") or e).get("title", "")
        items.append(f'<li><a href="{escape(e["date"])}.html">{escape(_date_ja(e["date"]))}　{escape(t)}</a>'
                     f'　<a class="meta" href="../#{escape(e["date"])}/ja">放送</a></li>')
    return "\n".join(['<!doctype html><html lang="ja"><head><meta charset="utf-8">',
                      '<meta name="viewport" content="width=device-width,initial-scale=1">',
                      f"<title>実践ガイド一覧</title><style>{CSS}</style></head><body><main>",
                      '<header class="top"><a class="btn primary" href="../">▶ 最新の放送</a></header>',
                      "<h1>実践ガイド一覧</h1><ul>", *items, "</ul></main></body></html>"])
