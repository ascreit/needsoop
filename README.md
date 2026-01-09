# NeedScoop

**SNSの生の声からSaaSアイデアの種を発見するツール**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## 🎯 What is NeedScoop?

NeedScoopは、Bluesky等のSNSから**ユーザーの不満・欲求・要望**をリアルタイムで収集し、ベクトル分析とクラスタリングによって**売れそうなSaaS/アプリのアイデア**を自動で発見・優先度付けするツールです。

### なぜ作ったか

- Reddit や Hacker News の「アイデア投稿」は既に誰かが言語化したもの → 二番煎じになりやすい
- **生の不満**（"I wish there was...", "frustrated with..."）から掘り起こすことで、まだ誰も気づいていないニーズを発見できる

## ✨ Features

- 🔥 **Bluesky Firehose** からリアルタイムでデータ収集（API無料・制限なし）
- 🧠 **ベクトルDB (ChromaDB)** によるセマンティック検索
- 📊 **UMAP + HDBSCAN** による自動クラスタリング
- 🎯 **優先度スコアリング** でアイデアをランク付け
- 📝 **企画書自動生成** （Markdown / PDF）

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Collectors    │────▶│    Analysis     │────▶│     Report      │
│                 │     │                 │     │                 │
│ • Bluesky       │     │ • Embedding     │     │ • Scoring       │
│ • G2/Capterra   │     │ • ChromaDB      │     │ • Markdown      │
│ • App Reviews   │     │ • Clustering    │     │ • PDF           │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        ▲                                               │
        │              cron (自動)                      │ 手動実行
        └───────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API Key（Embedding用）
- Anthropic API Key（レポート生成用、オプション）

### Installation

```bash
git clone https://github.com/yourusername/needscoop.git
cd needscoop
pip install -r requirements.txt
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml with your API keys
```

### Usage

```bash
# データ収集
python scripts/collect.py --limit 100      # 100件収集して停止
python scripts/collect.py --duration 300   # 5分間収集
python scripts/collect.py --stream         # 継続収集（Ctrl+Cで停止）

# 収集統計の確認
python scripts/collect.py --stats

# 分析実行（Phase 2で実装予定）
python scripts/analyze.py

# レポート生成（Phase 3で実装予定）
python scripts/report.py --output reports/$(date +%Y%m%d).md
```

#### 収集の目安

| 目的 | 推奨件数 | 所要時間 |
|------|---------|---------|
| 動作確認 | 100-500件 | 数分 |
| 初期分析 | 1,000-3,000件 | 30分〜数時間 |
| 本格運用 | 10,000件以上 | cron運用 |

## 📁 Project Structure

```
needscoop/
├── docs/
│   ├── DESIGN.md           # 設計企画書
│   ├── ARCHITECTURE.md     # アーキテクチャ詳細
│   └── SIGNALS.md          # 検出シグナル定義
├── src/
│   ├── collectors/
│   │   ├── base.py         # 収集基底クラス
│   │   ├── bluesky.py      # Bluesky Firehose
│   │   └── reviews.py      # G2/Capterra/App Store
│   ├── analysis/
│   │   ├── embeddings.py   # Embedding生成
│   │   ├── clustering.py   # UMAP + HDBSCAN
│   │   ├── scoring.py      # 優先度スコアリング
│   │   └── search.py       # セマンティック検索
│   ├── report/
│   │   ├── generator.py    # レポート生成
│   │   └── templates/      # テンプレート
│   └── db/
│       └── chroma.py       # ChromaDB操作
├── config/
│   ├── settings.yaml       # 設定ファイル
│   └── signals.yaml        # 検出シグナル定義
├── scripts/
│   ├── collect.py          # 収集スクリプト
│   ├── analyze.py          # 分析スクリプト
│   └── report.py           # レポート生成
├── data/
│   ├── chroma/             # Vector DB
│   └── reports/            # 出力レポート
├── tests/
├── requirements.txt
└── README.md
```

## 🔍 Detection Signals

NeedScoopは以下のようなフレーズを検出します：

```yaml
frustration:
  - "I wish there was"
  - "frustrated with"
  - "hate when"
  - "tired of"
  - "can't believe there's no"

desire:
  - "someone should build"
  - "looking for a tool that"
  - "does anyone know an app that"
  - "need something that"

problem:
  - "why isn't there"
  - "biggest pain point"
  - "waste so much time on"
```

## 📊 Output Example

```markdown
# SaaSアイデアレポート - 2025-01-09

## 🔴 HIGH Priority (Score 80+)

### 1. AI議事録の自動タスク化ツール
**Score**: 87/100
**検出数**: 156件
**代表的な声**:
- "Meeting transcripts are useless if I have to manually extract action items"
- "I wish there was something that automatically creates Jira tickets from meeting notes"

**競合状況**: Otter.ai, Fireflies.ai は文字起こしのみ、タスク化は手動
**推奨アクション**: Slack/Notion連携 + タスク自動生成のMVP検証
```

## 🛣️ Roadmap

### Phase 1: データ収集基盤 ✅
- [x] `src/collectors/base.py` - Post dataclass, BaseCollector ABC
- [x] `src/collectors/bluesky.py` - Bluesky Firehose収集
- [x] `src/analysis/signals.py` - シグナルパターンマッチング
- [x] `src/db/chroma.py` - ChromaDB操作
- [x] `scripts/collect.py` - 収集CLIスクリプト

### Phase 2: 分析基盤
- [ ] `src/analysis/embeddings.py` - OpenAI Embedding生成（バッチ処理）
- [ ] `src/analysis/clustering.py` - UMAP + HDBSCAN クラスタリング
- [ ] `scripts/analyze.py` - 分析実行スクリプト
- [ ] クラスタ可視化（matplotlib/plotly）

### Phase 3: スコアリング・レポート
- [ ] `src/analysis/scoring.py` - 優先度スコアリング（Claude API）
- [ ] `src/report/generator.py` - レポート生成
- [ ] `scripts/report.py` - レポート出力スクリプト
- [ ] Markdown / PDF 出力

### Phase 4: 拡張
- [ ] G2/Capterra スクレイピング
- [ ] Web UI（Streamlit）
- [ ] Slack通知連携
- [ ] cron設定ガイド

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.
