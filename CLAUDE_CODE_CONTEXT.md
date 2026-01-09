# NeedScoop - Claude Code 引き継ぎコンテキスト

## プロジェクト概要

**NeedScoop**は、SNS（主にBluesky）からユーザーの不満・欲求を収集し、SaaSアイデアの種を発見するツールです。

## 技術スタック

- Python 3.11+
- Bluesky AT Protocol (`atproto` ライブラリ)
- ChromaDB (Vector DB)
- OpenAI Embeddings (`text-embedding-3-small`)
- UMAP + HDBSCAN (クラスタリング)
- Claude API (レポート生成)

## 現在の状態

以下のファイルは作成済み：
- `README.md` - プロジェクト概要
- `docs/DESIGN.md` - 設計企画書（詳細）
- `config/signals.yaml` - 検出シグナル定義
- `config/settings.example.yaml` - 設定テンプレート
- `requirements.txt` - 依存関係
- `src/__init__.py` - パッケージ初期化
- `src/collectors/__init__.py` - コレクターサブパッケージ

## 次に実装すべきもの

### Phase 1 (MVP) の残タスク

1. **`src/collectors/base.py`** - コレクター基底クラス（途中）
   - `Post` dataclass
   - `BaseCollector` ABC

2. **`src/collectors/bluesky.py`** - Bluesky Firehose収集
   ```python
   # やること
   - AT Protocol Firehoseに接続
   - signals.yamlのパターンでフィルタリング
   - Post形式に正規化して返す
   ```

3. **`src/db/chroma.py`** - ChromaDB操作
   ```python
   # やること
   - コレクション作成/取得
   - Post保存（embedding含む）
   - セマンティック検索
   ```

4. **`src/analysis/signals.py`** - シグナル検出
   ```python
   # やること
   - signals.yamlを読み込み
   - テキストに対してパターンマッチ
   - signal_type, signal_matchesを返す
   ```

5. **`scripts/collect.py`** - 収集実行スクリプト

## 検出すべきシグナル例

```
"I wish there was"
"frustrated with"
"someone should build"
"why isn't there"
"looking for a tool that"
```

## Bluesky Firehose接続のサンプル

```python
from atproto import FirehoseSubscribeReposClient, parse_subscribe_repos_message

client = FirehoseSubscribeReposClient()

def on_message(message):
    commit = parse_subscribe_repos_message(message)
    for op in commit.ops:
        if op.action == 'create' and 'app.bsky.feed.post' in op.path:
            record = op.record
            text = getattr(record, 'text', '')
            # ここでシグナル検出 & 保存

client.start(on_message)
```

## 設計のポイント

- データ収集は自動（cron）、分析・レポートは手動実行
- ローカルファイルでMVP、サーバーは後回し
- Bluesky APIは無料・制限なしなので遠慮なく使う
- 月額コスト目標: $5以下（Embedding + Claude API）

## 参考リンク

- atproto Python SDK: https://github.com/MarshalX/atproto
- ChromaDB Docs: https://docs.trychroma.com/
- 設計詳細は `docs/DESIGN.md` を参照
