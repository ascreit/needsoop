# サービスアイデア調査ガイド

サービスアイデアの調査・提案を行う際は、このガイドに従う。

**まず [README.md](README.md) でプロジェクト概要を把握すること。**

---

## ゴール

**月10〜100万円の継続収益を生むサービスアイデアを見つける**

これは1回のセッションで終わる作業ではない。
セッションを跨いで試行錯誤を積み重ね、有望なアイデアに辿り着く。

---

## 過去の調査ログ（必ず確認）

`docs/research/logs/` に過去の調査記録がある。

- 何を試したか
- なぜダメだったか
- 次に何を試すべきか

**同じ失敗を繰り返さないために、まず過去ログを読むこと。**

過去ログを踏まえて：
- 対象サービスを変える
- 切り口を変える
- 検索ワードを変える
- 必要ならツールを開発する

など、次の一手を自分で考える。

---

## ナレッジ

| ファイル | 内容 |
|---------|------|
| [docs/knowledge/principles.md](docs/knowledge/principles.md) | 成功事例、基本原則、収益化3基準、失敗パターン |
| [docs/knowledge/idea-discovery.md](docs/knowledge/idea-discovery.md) | 発掘方法（パターンA/B/C）、検索クエリ例、連想フレームワーク |
| [docs/knowledge/validation-methods.md](docs/knowledge/validation-methods.md) | 検証方法（LP、直接セールス等） |
| [docs/knowledge/tips.md](docs/knowledge/tips.md) | 煮詰まったときの対処法 |

---

## 補助ツール（必要に応じて）

Web検索で賄えない場合、ツールを開発・使用する：

```bash
# Blueskyから日常の不満を収集
python scripts/collect.py --limit 1000
python scripts/extract_ideas.py
```

既存ツールで不十分なら、新しいツールを作ることも検討する。

---

## 調査後

調査結果は必ず `docs/research/logs/YYYYMMDD_[テーマ].md` に記録する。

記録する内容：
- 何を試したか（対象、切り口、検索ワード）
- 結果（見つかった不満、競合状況）
- なぜダメだったか / なぜ有望か
- 次に試すべきこと
