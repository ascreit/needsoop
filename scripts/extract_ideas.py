#!/usr/bin/env python3
"""
サービスアイデアになる困りごと投稿を抽出し、
ニーズの多さを分析するスクリプト
"""

import sys
from pathlib import Path
import re
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from src.db.chroma import PostStore
from src.analysis.clustering import PostClusterer
from sentence_transformers import SentenceTransformer


# スパム・ボット除外パターン
SPAM_PATTERNS = [
    r'#섹블|#섹트|#야방|#게이|#오프',  # 韓国語出会い系
    r'DMM.*販売中',  # DMMアフィリエイト
    r'www\.dmm\.com',
    r'plamofigure\.com',
    r'販売価格:\d+円',
    r'#PR\s*$',
    r'#フィギュア\s*#PR',
    r'予約受付中！',
    r'通販で販売中',
    r'○○○○○○',  # 意味不明な繰り返し
    r'ウオオオオオ',
    r'https://al\.dmm\.com',
    r'#AIart',
    r'#mlsb',  # 創作タグ
    r'🌸「|🛒「|🛒くん',  # 創作小説の会話形式
    r'youtube\.com|youtu\.be',  # YouTube宣伝
    r'netkeiba',  # 競馬ニュース
    r'コミティア|COMITIA',  # 同人イベント宣伝
    r'全肯定bot',  # bot
    r'キャラデザ|キャラクター',  # オタク創作
    r'二次創作',
    r'同人|頒布',
    r'推し|オタク',
    r'アニメ|漫画|マンガ',
    r'ゲーム|ガチャ|ピックアップ',
    r'フィギュア',
    r'ド癖|性癖',
    r'メティス|ガチャ石',  # ソシャゲ
    r'新刊.*冊',  # 同人誌
    r'お品書き',
]

# 困りごと・不満を示すキーワード
COMPLAINT_KEYWORDS = [
    '困', '面倒', 'めんどう', 'めんどくさ', 'つらい', '辛い', 'しんどい',
    '疲れ', 'つかれ', '大変', 'たいへん', '難し', 'むずかし',
    '不満', '不便', '嫌', 'いや', 'やだ', '無理', 'むり',
    '悩', 'なや', '問題', 'トラブル', 'イライラ', 'ストレス',
    '分からない', 'わからない', 'わかんない', 'できない', '出来ない',
    '欲しい', 'ほしい', 'してほしい', 'なんとか',
    '高い', '高すぎ', '時間がない', '時間かかる', '待た',
    'バグ', 'エラー', '動かない', '壊れ', '使えない', '落ち',
]

# オタク・創作系の追加除外パターン
OTAKU_PATTERNS = [
    r'描い[たて]', r'書い[たて]',  # 創作活動
    r'〆切|締め切り|入稿',
    r'原稿',
    r'イベント|即売会',
    r'絵師|作家',
    r'本.*出[すし]',
    r'サークル',
    r'スペース',
]


def is_spam(text: str) -> bool:
    """スパム・ボット投稿かどうか判定"""
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def is_otaku_content(text: str) -> bool:
    """オタク・創作系コンテンツか判定"""
    for pattern in OTAKU_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def has_complaint_keyword(text: str) -> bool:
    """困りごとキーワードを含むか判定"""
    for keyword in COMPLAINT_KEYWORDS:
        if keyword in text:
            return True
    return False


def is_japanese(text: str) -> bool:
    """日本語を含むか判定（中国語を除外）"""
    # ひらがな・カタカナが一定数あるか（漢字のみだと中国語の可能性）
    hiragana = len(re.findall(r'[\u3040-\u309F]', text))
    katakana = len(re.findall(r'[\u30A0-\u30FF]', text))
    return (hiragana + katakana) >= 3


def main():
    store = PostStore(persist_directory=Path("data/chroma"))
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    # 複数のクエリで検索
    queries = [
        "困っている 大変 面倒くさい",
        "〜できなくて困る",
        "不便 使いにくい 分かりにくい",
        "疲れた しんどい つらい",
        "こうだったらいいのに 欲しい",
        "問題 トラブル 解決したい",
    ]

    all_results = {}

    print("検索中...")
    for query in queries:
        query_embedding = model.encode(query).tolist()
        results = store.search(query_embedding=query_embedding, n_results=2000)

        for post, score in results:
            if post.id not in all_results or score < all_results[post.id][1]:
                all_results[post.id] = (post, score)

    print(f"検索結果（重複除去後）: {len(all_results)}件")

    # フィルタリング
    filtered = []
    for post, score in all_results.values():
        # スコア閾値（低いほど類似度高い）
        if score > 0.85:
            continue

        # スパム除外
        if is_spam(post.text):
            continue

        # オタク・創作系除外
        if is_otaku_content(post.text):
            continue

        # 日本語のみ
        if not is_japanese(post.text):
            continue

        # 困りごとキーワードを含む（スコアが低い＝類似度高い場合は免除）
        if score > 0.6 and not has_complaint_keyword(post.text):
            continue

        filtered.append((post, score))

    print(f"フィルタ後: {len(filtered)}件")

    if len(filtered) < 10:
        print("困りごと投稿が少なすぎます。")
        return

    # クラスタリング用のembedding取得
    print("\nクラスタリング中...")
    embeddings_dict = store.get_embeddings()

    posts_with_emb = []
    embeddings = []
    for post, score in filtered:
        if post.id in embeddings_dict:
            posts_with_emb.append((post, score))
            embeddings.append(embeddings_dict[post.id])

    embeddings_array = np.array(embeddings)

    # クラスタリング実行
    clusterer = PostClusterer(min_cluster_size=3)
    result = clusterer.fit(embeddings_array)

    print(f"クラスタ数: {result.n_clusters}")
    print(f"ノイズ: {result.n_noise}件")

    # 各クラスタの投稿を収集
    cluster_posts = defaultdict(list)
    for i, (post, score) in enumerate(posts_with_emb):
        cluster_id = result.labels[i]
        if cluster_id != -1:  # ノイズ以外
            cluster_posts[cluster_id].append((post, score))

    # クラスタをサイズ順にソート
    sorted_clusters = sorted(
        cluster_posts.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )

    # 結果表示
    print("\n" + "=" * 80)
    print("【ニーズ分析結果】サイズ順（同じ悩みを持つ人が多い順）")
    print("=" * 80)

    for cluster_id, posts in sorted_clusters:
        # クラスタの注目度（いいね・リポスト合計）
        total_engagement = sum(p.likes + p.reposts for p, _ in posts)
        avg_engagement = total_engagement / len(posts) if posts else 0

        print(f"\n### クラスタ {cluster_id}: {len(posts)}件 (平均エンゲージメント: {avg_engagement:.1f})")
        print("-" * 40)

        # サンプル表示（最大5件）
        for i, (post, score) in enumerate(posts[:5], 1):
            text = post.text.replace("\n", " ")[:150]
            engagement = f"[♥{post.likes} 🔁{post.reposts}]" if post.likes or post.reposts else ""
            print(f"  {i}. {engagement} {text}...")

        if len(posts) > 5:
            print(f"  ... 他 {len(posts) - 5}件")

    # サマリー
    print("\n" + "=" * 80)
    print("【サマリー】")
    print("=" * 80)
    print(f"総困りごと投稿数: {len(filtered)}件")
    print(f"クラスタ数: {result.n_clusters}")
    print(f"上位3クラスタ:")
    for i, (cluster_id, posts) in enumerate(sorted_clusters[:3], 1):
        sample_text = posts[0][0].text.replace("\n", " ")[:80]
        print(f"  {i}. {len(posts)}件 - 例: {sample_text}...")


if __name__ == "__main__":
    main()
