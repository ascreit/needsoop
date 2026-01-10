#!/usr/bin/env python3
"""
クラスタリング結果から一般の日常会話クラスタを抽出するテストスクリプト
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv
import numpy as np
from src.db.chroma import PostStore
from src.analysis.clustering import PostClusterer
import openai

load_dotenv()


def main():
    # データ読み込み
    store = PostStore(persist_directory=Path("data/chroma"))

    query = "日常での困りごと、不満"
    results = store.search(query=query, n_results=1000)

    embeddings_dict = store.get_embeddings()

    posts_with_emb = []
    embeddings = []
    for post, score in results:
        if post.id in embeddings_dict:
            posts_with_emb.append((post, score))
            embeddings.append(embeddings_dict[post.id])

    print(f"投稿数: {len(posts_with_emb)}")

    # クラスタリング実行
    embeddings_array = np.array(embeddings)
    clusterer = PostClusterer(min_cluster_size=5)
    result = clusterer.fit(embeddings_array)

    print(f"クラスタ数: {result.n_clusters}")
    print(f"ノイズ: {result.n_noise}件")

    # 各クラスタの全投稿を収集
    cluster_posts = {}
    for cluster_id in sorted(set(result.labels)):
        if cluster_id == -1:
            continue
        indices = [i for i, l in enumerate(result.labels) if l == cluster_id]
        cluster_posts[cluster_id] = [posts_with_emb[idx][0] for idx in indices]

    print(f"\nクラスタサイズ:")
    for cid, posts in cluster_posts.items():
        print(f"  クラスタ {cid}: {len(posts)}件")

    # GPTに判定させるプロンプト作成（各クラスタ5件のみ）
    prompt = """以下は投稿をクラスタリングした結果です。各クラスタのサンプルを見て、「一般の人の日常会話・困りごと・つぶやき」に該当するクラスタ番号を特定してください。

ボット投稿、スパム、広告、ニュース、創作小説などは除外してください。

"""

    for cid, posts in cluster_posts.items():
        prompt += f"\n=== クラスタ {cid} ({len(posts)}件) ===\n"
        for i, post in enumerate(posts[:5], 1):  # LLMには5件のみ
            text = post.text.replace("\n", " ")[:300]
            prompt += f"{i}. {text}\n"

    prompt += """

以下のJSON形式で回答してください：
{
  "clusters": [
    {"id": クラスタ番号, "reason": "選定理由"},
    ...
  ]
}
"""

    # GPTに判定させる
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print("\n=== GPTに判定を依頼中... ===")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    gpt_response = response.choices[0].message.content
    print(f"\nGPT回答:\n{gpt_response}")

    # JSONをパース
    import json

    try:
        result = json.loads(gpt_response)
        clusters_info = result.get("clusters", [])

        print(f"\n=== 選定されたクラスタ ===")
        for info in clusters_info:
            print(f"クラスタ {info['id']}: {info['reason']}")

        # クラスタIDと理由の辞書を作成
        cluster_reasons = {info["id"]: info["reason"] for info in clusters_info}
        cluster_ids = list(cluster_reasons.keys())
        print(f"\n抽出されたクラスタ番号: {cluster_ids}")

        # 該当クラスタの全投稿を表示
        for cid in cluster_ids:
            if cid in cluster_posts:
                posts = cluster_posts[cid]
                reason = cluster_reasons.get(cid, "")
                print(f"\n{'='*80}")
                print(f"=== クラスタ {cid} の全投稿 ({len(posts)}件) ===")
                print(f"理由: {reason}")
                print(f"{'='*80}")
                for i, post in enumerate(posts, 1):
                    text = post.text.replace("\n", " ")
                    print(f"\n{i}. {text}")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"JSONパースエラー: {e}")


if __name__ == "__main__":
    main()
