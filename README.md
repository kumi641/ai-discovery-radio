# AI Discovery & Build Radio

**AIの進化を、自分の制作・開発に変えるための朝の番組。**
毎朝7時（日本時間）、GitHub Actions が最新のAI情報を集め、Claude が一次情報を確かめて選び、
「何が新しいか → 何に使えるか → 今日すぐ試せること」まで台本と実践ガイドにします。
Azure の合成音声で読み上げ、GitHub Pages で放送し、GitHub Releases のメール通知で届きます。PC の電源は不要です。

- 放送：https://kumi641.github.io/ai-discovery-radio/
- 実践ガイド一覧：https://kumi641.github.io/ai-discovery-radio/guides/

プレーヤーと番組の形は、[ものラジオ](https://github.com/monoradio102/myradio)のテンプレート（MIT）をそのまま使っています。

## 仕組み

```
毎時起動 ─ gate ─(設定時刻を過ぎていて、今日の回がまだ無い)─┐
                                                          ▼
generate（読み取り専用。シークレットは Claude の OAuth トークンだけ）
  1. radio.collect   config/sources.yaml の RSS・公開API → work/candidates.json（公開日時のない記事は除外）
  2. Claude Code     prompts/editor.md に従い、一次情報を WebFetch で確認 → 採点・選別・台本・実践課題
                     → work/draft.json（Bash は禁止。外部ページの文章は命令として扱わない）
  3. radio.validate  形の検査（壊れていれば Claude に1回だけ修正を依頼）
                                                          ▼
publish（コードはチェックアウトし直す。Claude の出力は JSON データとしてだけ受け取る）
  4. radio.validate  ニュースの URL は収集した候補のものだけ／全 URL が開くか／公開日時が範囲内か
  5. radio.build     番組 JSON（monoradio/news-1）＋ リンクカード（各サイトの OGP 画像の URL）
  6. radio.tts       Azure AI Speech F0 で1文ずつ合成 → 秒を正確に計測 → FFmpeg で MP3（音量をそろえる）
  7. radio.build     実践ガイド（Markdown / HTML）・履歴・実行ログ
  8. main にコミット → tools/publish.sh で gh-pages を作り直す（音声は直近30日分だけ。main には入れない）
  9. radio.site      公開された URL を確認 → GitHub Release を作成（＝メール通知）
```

どこかで失敗したら、その時点で止まり、公開しません。同じ日の回は1つだけ（再実行しても Release は重複しません）。

## ファイル

```
config/settings.yaml   放送時刻・本数・長さ・声・上限値
config/sources.yaml    情報源（RSS / html_links / Hacker News / HF Daily Papers）
config/topics.yaml     関心領域・採点基準・コーナー・実践提案の方針
prompts/editor.md      Claude への編集方針（台本と実践ガイドの中身はここで決まる）
radio/                 収集・検証・組立・音声・ガイド・公開確認（Python）
tests/                 pytest
.github/workflows/     broadcast.yml（毎日の放送）、test.yml（テスト）
index.html             プレーヤー（ものラジオ。実践ガイドへのボタンを追加）
episodes/ episodes.json 台本とタイミング（公開）
guides/                実践ガイド（公開）
data/history.json      扱ったニュースと実験（重複防止）
data/tts_usage.json    音声の月ごとの文字数
data/runs/             毎回の実行ログ（情報源ごとの成否、採点、警告）
private/               実践ログ（.gitignore 済み。GitHub に載らない）
```

## 必要な認証情報（GitHub の Settings → Secrets and variables → Actions）

| Secret | 用途 | 入手方法 |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | 台本生成（Claude Max の利用枠） | 手元で `claude setup-token` を実行 |
| `AZURE_SPEECH_KEY` | 音声合成 | Azure ポータルで Speech リソース（価格レベル **Free F0**）を作り、「キーとエンドポイント」のキー |
| `AZURE_SPEECH_REGION` | 同上 | 同じ画面のリージョン（例：`japaneast`） |

`GITHUB_TOKEN` は自動で用意されます（追加不要）。

## 設定を変える

- 放送時刻：`config/settings.yaml` の `schedule.time`（ワークフローの変更は不要）
- 本数・長さ：`program`
- 声：`tts.voices.main`（例：`ja-JP-NanamiNeural`、`ja-JP-KeitaNeural`）
- 情報源：`config/sources.yaml` に1行足す／`enabled: false` で止める
- 関心領域や採点の重み：`config/topics.yaml`
- 番組の語り口や実践課題の深さ：`prompts/editor.md`

## 手元で試す

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
python -m radio.collect            # work/candidates.json
python -m radio.tts --provider fake episodes/<日付>-ja.json   # 無音の音声で流れだけ確認
```

## ライセンスとクレジット

- プログラム：MIT（`index.html` と `tools/` は monoradio102/myradio のもの。LICENSE 参照）
- キャラクター（`character/`）：myradio のキャラクター（公序良俗に反しない範囲で自由に使えると明記されています）
- 声：Microsoft Azure AI Speech（合成音声）
- 台本・実践ガイド：公開情報をもとに Claude が作成。手順・コマンド・料金は必ず出典で確認してください
