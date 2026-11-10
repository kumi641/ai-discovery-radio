# キャラクターの変え方

プレーヤーは `character/character.json` を読んで、キャラを表示します（形の詳細は [formats.md](formats.md)）。

## いまのキャラ

AI（Codex）で生成した絵です。口パクとまばたきの差分も、Codex CLI の画像生成で「同じ絵の口・目だけを描き変える」ように頼んで作りました（`codex exec -i 元の絵.png "…口を閉じた版を同じ構図で…"`）。元の絵と画素単位で位置がそろっていることを確かめてから切り出しています。

## 1. いちばん簡単：1 枚絵だけ

1. 背景が**本当に透明**な PNG を用意する（市松模様が「絵として」描かれた画像は不可。下の「背景の透明化」）
2. 896×768 ピクセルに収める（上半身〜ひざくらいまでが映る横長の枠）
3. `character/base.png` を置き換える
4. `character/character.json` は次のままでよい

```json
{"format": "myradio/character-1", "type": "sprites", "size": [896, 768], "background": "#161a26", "base": "base.png", "parts": {}}
```

5. コミットして push し、Actions の **publish-site** を実行すると（または次の放送で）サイトに反映されます

この形では、口とまばたきは動きません（体の揺れ・視線の向きは動きます）。

## 2. 口パク・まばたきを付ける（差分画像）

同じ絵の「口だけ」「目だけ」を描き変えた画像を用意します。画像生成 AI の編集機能（例：「この画像の口を閉じて」「目を閉じて」）で作れます。**輪郭・位置・大きさを変えずに**描き変えるのがコツです。

| ファイル | 中身 | 用途 |
|---|---|---|
| `base.png` | **口を閉じた**正面の絵（全体） | いつもの姿 |
| `mouth_half.png` | 口のまわりだけ切り出した「半開き」 | 話している途中 |
| `mouth_open.png` | 口のまわりだけ切り出した「開き」 | 話している途中 |
| `blink.png` | 目のまわりだけ切り出した「閉じた目」 | まばたき |
| `half_blink.png` | （任意）半目 | まばたきを滑らかに |
| `smile_mouth.png` | （任意）笑顔の口 | エンディング |

切り出した画像を `base.png` のどこに重ねるか（左上の x, y）を `character.json` に書きます。

```json
{
 "format": "myradio/character-1", "type": "sprites", "size": [896, 768], "background": "#161a26",
 "base": "base.png",
 "parts": {
  "mouth_half": {"src": "mouth_half.png", "x": 400, "y": 250},
  "mouth_open": {"src": "mouth_open.png", "x": 400, "y": 250},
  "blink":      {"src": "blink.png",      "x": 330, "y": 180}
 },
 "mouth": {"1": "mouth_half", "2": "mouth_open"},
 "eye": {"blink": "blink"}
}
```

**いちばん簡単な頼み方**：全体の絵を 3 枚（口を閉じた絵、口を開けた絵、目を閉じた絵）作って、Claude Code に「character/ の差分にして」と頼めば、切り出しと座標の計算はこちらで行えます。

## 背景の透明化

AI で作った画像は、透明に見えても市松模様が描き込まれていることがあります。

- remove.bg（https://www.remove.bg/ja）、Canva の背景除去、iPhone / Mac の「被写体を持ち上げる」などで透明 PNG にする
- 輪郭線がはっきりしたイラストなら、Claude Code に頼めば外側の背景を透明にできます（今回の `base.png` はこの方法）

## 権利

自分で作ったか、利用が許されている絵だけを使ってください。AI で作ったキャラは `station.json` の `character.note` にそう書きます。
