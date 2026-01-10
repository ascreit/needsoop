#!/usr/bin/env python3
"""
テスト用のセマンティック検索スクリプト
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.chroma import PostStore
from sentence_transformers import SentenceTransformer

def main():
    # データ読み込み
    store = PostStore(persist_directory=Path("data/chroma"))

    # ローカルembeddingモデル（多言語対応）
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    query = "日常での困りごと、不満"
    query_embedding = model.encode(query).tolist()
    results = store.search(query_embedding=query_embedding, n_results=1000)

    print(f"検索結果: {len(results)}件\n")
    # 表示
    for i, (post, score) in enumerate(results):
        text = post.text
        print(f'{i+1}. [{score:.3f}] {text}')


if __name__ == "__main__":
    main()
