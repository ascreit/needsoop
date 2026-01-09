# NeedScoop 設計企画書

> SNSの生の声からSaaSアイデアの種を発見するシステム

**Version**: 1.0  
**Last Updated**: 2025-01-09

---

## 1. エグゼクティブサマリー

### 1.1 目的

NeedScoopは、SNS上の**生の不満・欲求**からSaaS/アプリのアイデアを発見するツールです。

従来のアプローチ（Reddit, Hacker News等）では「すでに言語化されたアイデア」を拾うため、二番煎じになりやすい問題がありました。NeedScoopは「I wish there was...」「frustrated with...」といった**生の声**を収集・分析することで、まだ誰も気づいていないニーズを発見します。

### 1.2 特徴

| 特徴 | 説明 |
|------|------|
| 生データ重視 | アイデア投稿ではなく、不満・欲求の生の声を収集 |
| ベクトル分析 | セマンティック検索でトレンドの意味的類似性を把握 |
| 自動クラスタリング | 関連する声を自動グループ化、トレンド検出 |
| 優先度スコアリング | AIによる市場性・実現可能性の評価 |

---

## 2. システムアーキテクチャ

### 2.1 全体構成

```
┌─────────────────────────────────────────────────────────────────┐
│                         NeedScoop                                │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   収集層        │    分析層        │         出力層              │
│   (自動/cron)   │    (手動/自動)   │         (手動)              │
├─────────────────┼─────────────────┼─────────────────────────────┤
│                 │                 │                             │
│ Bluesky         │ Embedding       │ Claude API                  │
│ Firehose        │ (OpenAI)        │                             │
│                 │                 │ ┌─────────────────────────┐ │
│ G2/Capterra     │ ChromaDB        │ │ 企画書生成              │ │
│ (将来)          │ (Vector DB)     │ │ • Markdown              │ │
│                 │                 │ │ • PDF                   │ │
│ App Store       │ HDBSCAN         │ │ • 優先度ランキング      │ │
│ Reviews (将来)  │ Clustering      │ └─────────────────────────┘ │
│                 │                 │                             │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

### 2.2 技術スタック

| レイヤー | 技術 | 選定理由 |
|----------|------|----------|
| 言語 | Python 3.11+ | ML/NLPライブラリが充実 |
| Vector DB | ChromaDB | ローカル動作、軽量、SQLite互換 |
| Embedding | OpenAI `text-embedding-3-small` | コスト効率、多言語対応 |
| クラスタリング | UMAP + HDBSCAN | クラスタ数自動決定、ノイズ耐性 |
| LLM | Claude 3.5 Sonnet | 長文コンテキスト、日本語品質 |
| スケジューラ | cron / systemd timer | シンプル、ローカル完結 |

---

## 3. データ収集設計

### 3.1 Bluesky Firehose（メインソース）

Blueskyの全公開投稿をリアルタイムでストリーム取得できます。

**メリット**:
- ✅ API完全無料、レート制限なし
- ✅ 全データアクセス可能（Firehose）
- ✅ テック系アーリーアダプター層が多い
- ✅ 英語圏中心でグローバル市場向け

**接続方法**:

```python
from atproto import FirehoseSubscribeReposClient, parse_subscribe_repos_message
from atproto.exceptions import FirehoseError

def on_message(message):
    commit = parse_subscribe_repos_message(message)
    for op in commit.ops:
        if op.action == 'create' and op.path.startswith('app.bsky.feed.post'):
            record = op.record
            if matches_signal(record.text):
                save_to_db(record)

client = FirehoseSubscribeReposClient()
client.start(on_message)
```

### 3.2 検出シグナル

以下のフレーズ/パターンを検出対象とします：

```yaml
# config/signals.yaml

frustration:
  patterns:
    - "I wish there was"
    - "I wish someone would build"
    - "frustrated with"
    - "hate when"
    - "tired of"
    - "can't believe there's no"
    - "why is it so hard to"
    - "waste so much time on"
  weight: 1.0

desire:
  patterns:
    - "someone should build"
    - "looking for a tool that"
    - "does anyone know an app"
    - "need something that"
    - "would pay for"
    - "take my money"
  weight: 1.2  # 購買意欲が明確

problem:
  patterns:
    - "why isn't there"
    - "biggest pain point"
    - "most annoying thing about"
    - "if only there was"
  weight: 0.9

comparison:
  patterns:
    - "better alternative to"
    - "like X but"
    - "X is too expensive"
    - "X doesn't have"
  weight: 1.1  # 競合の弱点
```

### 3.3 データスキーマ

```python
@dataclass
class Post:
    id: str                    # "bsky_{cid}"
    source: str                # "bluesky"
    text: str                  # 本文
    author_did: str            # 投稿者DID
    created_at: datetime       # 投稿日時
    collected_at: datetime     # 収集日時
    
    # 分析結果
    signal_type: str           # "frustration", "desire", etc.
    signal_matches: list[str]  # マッチしたパターン
    embedding: list[float]     # 1536次元ベクトル
    cluster_id: int            # クラスタID (-1 = ノイズ)
    
    # メタデータ
    likes: int
    reposts: int
    replies: int
    language: str              # 言語検出結果
```

### 3.4 将来の拡張ソース

| 優先度 | ソース | データ内容 | 実装難易度 |
|--------|--------|-----------|-----------|
| P1 | G2/Capterra | SaaSレビューの「Cons」 | 中（スクレイピング） |
| P1 | App Store | アプリの低評価レビュー | 中 |
| P2 | Mastodon | Fediverse全体 | 低（API公開） |
| P2 | X (Twitter) | 最大ボリューム | 高（$100/月） |

---

## 4. ベクトル分析設計

### 4.1 Embedding戦略

投稿テキストをそのままEmbeddingに変換します。短文が多いため、要約は不要です。

```python
import openai

def create_embedding(text: str) -> list[float]:
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding
```

**コスト見積もり**:
- 1投稿 ≈ 100 tokens
- 10,000投稿/日 × 30日 = 300,000投稿/月
- 30M tokens × $0.02/1M = **$0.60/月**

### 4.2 ChromaDB設計

```python
import chromadb

client = chromadb.PersistentClient(path="./data/chroma")

collection = client.get_or_create_collection(
    name="posts",
    metadata={"hnsw:space": "cosine"}  # コサイン類似度
)

# 保存
collection.add(
    ids=[post.id],
    embeddings=[post.embedding],
    documents=[post.text],
    metadatas=[{
        "source": post.source,
        "signal_type": post.signal_type,
        "created_at": post.created_at.isoformat(),
        "likes": post.likes
    }]
)

# セマンティック検索
results = collection.query(
    query_texts=["AI meeting transcription automation"],
    n_results=50,
    where={"signal_type": "frustration"}
)
```

### 4.3 クラスタリング

UMAP（次元削減）+ HDBSCAN（密度ベースクラスタリング）を使用します。

```python
import umap
import hdbscan
import numpy as np

def cluster_posts(embeddings: np.ndarray) -> np.ndarray:
    # 1536次元 → 50次元に削減
    reducer = umap.UMAP(
        n_components=50,
        n_neighbors=15,
        min_dist=0.1,
        metric='cosine'
    )
    reduced = reducer.fit_transform(embeddings)
    
    # クラスタリング
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=10,      # 最低10件で1クラスタ
        min_samples=5,
        cluster_selection_epsilon=0.5
    )
    labels = clusterer.fit_predict(reduced)
    
    return labels  # -1 = ノイズ（どのクラスタにも属さない）
```

**パラメータの意味**:
- `min_cluster_size=10`: 最低10件の類似投稿がないとクラスタ化しない
- `min_samples=5`: コア点となるための最低近傍数
- `-1`ラベル: ノイズとして除外（単発の投稿）

---

## 5. 優先度スコアリング

### 5.1 スコア構成

| 指標 | 重み | 算出方法 |
|------|------|----------|
| ボリューム | 25% | クラスタ内の投稿数（対数スケール） |
| エンゲージメント | 20% | いいね・リポスト・リプライの合計 |
| 成長速度 | 20% | 直近7日 vs 前7日の投稿増加率 |
| 明確性 | 20% | LLM判定：ペインポイントの具体性 |
| 収益化可能性 | 15% | LLM判定：B2B/B2C、課金モデル適合 |

### 5.2 スコアリングプロンプト

```python
SCORING_PROMPT = """
以下のクラスタ（ユーザーの声の集合）を評価してください。

## クラスタ概要
{cluster_summary}

## 代表的な投稿
{sample_posts}

## 評価基準
1. **明確性** (0-100): ペインポイントは具体的か？何を解決すべきか明確か？
2. **市場性** (0-100): 十分な市場規模があるか？誰が顧客か？
3. **収益化** (0-100): SaaSとして課金できるか？B2B/B2C？
4. **競合状況** (0-100): 既存ソリューションの有無、差別化余地
5. **実現可能性** (0-100): 技術的難易度、必要リソース

## 出力形式（JSON）
{
  "clarity": 75,
  "market": 60,
  "monetization": 80,
  "competition": 70,
  "feasibility": 85,
  "total_score": 74,
  "idea_name": "提案するプロダクト名",
  "one_liner": "一言で表す価値提案",
  "target_customer": "想定顧客",
  "reasoning": "評価の根拠（2-3文）"
}
"""
```

---

## 6. 出力設計

### 6.1 レポートフォーマット

```markdown
# SaaSアイデアレポート

**生成日**: 2025-01-09
**分析期間**: 2025-01-02 〜 2025-01-09
**収集投稿数**: 12,345件
**検出クラスタ数**: 47個
**推奨アイデア数**: 12個

---

## 🔴 HIGH Priority (Score 80+)

### 1. [アイデア名]

| 項目 | 値 |
|------|-----|
| **スコア** | 87/100 |
| **検出数** | 156件 |
| **シグナル** | frustration (68%), desire (32%) |
| **成長率** | +45% (vs 前週) |

#### 概要
{ai_generated_summary}

#### 代表的な声
> "Meeting transcripts are useless if I have to manually extract action items"
> — @user1, 2025-01-08, ❤️ 234

> "I wish there was something that automatically creates Jira tickets from meeting notes"
> — @user2, 2025-01-07, ❤️ 189

#### 競合分析
- **Otter.ai**: 文字起こしのみ、タスク化は手動
- **Fireflies.ai**: 要約機能あり、タスク連携なし
- **差別化ポイント**: Slack/Jira/Asana直接連携 + 自動タスク生成

#### 推奨アクション
1. Slack連携のMVP（2週間）
2. 10社へのユーザーインタビュー
3. ランディングページでの需要検証

---

## 🟡 MEDIUM Priority (Score 60-79)
...

## 🟢 LOW Priority (Score 40-59)
...

---

## 付録: クラスタ一覧

| ID | 投稿数 | スコア | キーワード |
|----|--------|--------|-----------|
| 1 | 156 | 87 | meeting, transcript, action items |
| 2 | 98 | 72 | invoice, automation, quickbooks |
...
```

### 6.2 出力形式

- **Markdown**: GitHub、Notion、Obsidian等で閲覧
- **PDF**: pandocで変換、共有用
- **JSON**: プログラムからの参照用

---

## 7. 開発ロードマップ

### Phase 1: データ収集基盤（Week 1-2）

**目標**: Bluesky Firehoseから生データを収集し、ChromaDBに保存

- [ ] プロジェクトセットアップ（pyproject.toml, 依存関係）
- [ ] Bluesky AT Protocol クライアント実装
- [ ] シグナル検出ロジック（正規表現 + キーワードマッチ）
- [ ] ChromaDB セットアップ（永続化モード）
- [ ] cron設定（バックグラウンド収集）

**成果物**: 1日1,000件以上の投稿を自動収集

### Phase 2: 分析基盤（Week 3-4）

**目標**: Embeddingとクラスタリングで意味的なグループ化

- [ ] OpenAI Embedding API連携（バッチ処理）
- [ ] UMAP + HDBSCAN パイプライン構築
- [ ] クラスタ可視化（matplotlib / plotly）
- [ ] セマンティック検索CLI

**成果物**: 類似した声が自動グループ化される

### Phase 3: スコアリング・レポート（Week 5-6）

**目標**: 優先度付きの企画書を自動生成

- [ ] Claude API連携（スコアリング）
- [ ] レポートテンプレート作成
- [ ] Markdown / PDF出力
- [ ] CLIコマンド整備

**成果物**: 週次レポートの自動生成

### Phase 4: 拡張（Week 7-8）

- [ ] G2/Capterra スクレイピング追加
- [ ] Web UI（Streamlit or Gradio）
- [ ] Slack通知連携
- [ ] パラメータチューニング

---

## 8. コスト見積もり（月額）

| 項目 | 単価 | 想定使用量 | 月額 |
|------|------|-----------|------|
| OpenAI Embedding | $0.02/1M tokens | 30M tokens | ~$0.60 |
| Claude API | $3/1M input | 500K tokens | ~$1.50 |
| Bluesky API | 無料 | - | $0 |
| サーバー（ローカル） | - | - | $0 |
| **合計** | | | **~$2.10** |

※ 本番運用時（クラウドサーバー）でも月額 $10-20 程度

---

## 9. リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| Bluesky API仕様変更 | 収集停止 | AT Protocolは安定、公式ライブラリ使用 |
| ノイズ過多 | 分析精度低下 | シグナルパターンの継続的チューニング |
| クラスタ品質 | 無意味なグループ化 | min_cluster_size調整、手動レビュー |
| API費用増大 | コスト超過 | バッチ処理、キャッシュ活用 |

---

## 10. 次のステップ

### 今すぐ着手できるタスク

| # | タスク | 所要時間 |
|---|--------|----------|
| 1 | GitHubリポジトリ作成、初期構成 | 30分 |
| 2 | `atproto` ライブラリ動作確認 | 1時間 |
| 3 | Firehoseから100件取得するスクリプト | 2時間 |
| 4 | シグナル検出の正規表現実装 | 2時間 |
| 5 | ChromaDBに保存する処理 | 2時間 |

---

## Appendix A: 参考リンク

- [Bluesky AT Protocol Docs](https://atproto.com/)
- [atproto Python SDK](https://github.com/MarshalX/atproto)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [HDBSCAN Documentation](https://hdbscan.readthedocs.io/)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
