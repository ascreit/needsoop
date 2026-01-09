# NeedScoop TODO

## 現在の状況

- **Phase 1 完了**: データ収集基盤が動作中
- **収集中**: `python scripts/collect.py --stream` で継続収集可能

---

## Phase 2: 分析基盤（次のタスク）

### 高優先度
- [ ] `src/analysis/embeddings.py` - OpenAI Embedding生成
  - バッチ処理（100件ずつ）
  - 既存投稿へのEmbedding追加
  - コスト: 約$0.60/月（30万投稿想定）

- [ ] `src/analysis/clustering.py` - クラスタリング
  - UMAP: 1536次元 → 50次元に次元削減
  - HDBSCAN: min_cluster_size=10 で自動クラスタ検出
  - cluster_id を ChromaDB に保存

- [ ] `scripts/analyze.py` - 分析実行スクリプト
  - Embedding未生成の投稿を処理
  - クラスタリング実行
  - 統計出力

### 中優先度
- [ ] クラスタ可視化
  - matplotlib/plotly で2D散布図
  - クラスタごとの色分け
  - 代表的なキーワード表示

---

## Phase 3: スコアリング・レポート

- [ ] `src/analysis/scoring.py` - Claude APIでスコアリング
  - 明確性、市場性、収益化可能性、競合状況、実現可能性
  - クラスタごとに評価

- [ ] `src/report/generator.py` - レポート生成
  - Markdown テンプレート
  - 優先度別セクション (HIGH/MEDIUM/LOW)
  - 代表的な投稿の引用

- [ ] `scripts/report.py` - レポート出力
  - Markdown出力
  - PDF変換（pandoc）

---

## Phase 4: 拡張

### データ管理
- [ ] `scripts/rescan.py` - 再スキャンスクリプト
  - 既存データを新しいシグナルパターンで再分類
  - 言語学習サービス等、別用途への転用にも対応

### デプロイ
- [ ] Fly.io + 永続Volume でデプロイ（最安構成）
  - Dockerfile作成
  - cron設定（収集の自動化）
  - 永続ディスク設定
- [ ] データ増加時は Pinecone へ移行検討
  - ChromaDB → Pinecone アダプタ作成
  - 無料枠: 100K vectors

### 機能拡張
- [ ] G2/Capterra スクレイピング
- [ ] Web UI（Streamlit）
- [ ] Slack通知連携

---

## 技術的な改善

- [ ] テスト追加（pytest）
- [ ] 型チェック（mypy）
- [ ] ログローテーション設定
- [ ] 設定ファイルのバリデーション

---

## メモ

### 収集の目安
| 目的 | 件数 | 時間 |
|-----|------|------|
| テスト | 100-500 | 数分 |
| 初期分析 | 1,000-3,000 | 30分〜数時間 |
| 本格運用 | 10,000+ | cron |

### 月額コスト見積もり
- OpenAI Embedding: ~$0.60
- Claude API: ~$1.50
- **合計: ~$2.10/月**
