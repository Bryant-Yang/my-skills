#!/usr/bin/env python3
"""
从 prompts.json 中搜索与用户描述最相关的 prompt，返回 Top N 结果。
用法: python3 search_prompts.py "用户描述" [top_n=3]
"""

import json, sys, re
from pathlib import Path

def tokenize(text):
    text = text.lower()
    # 中英文分词：英文按空格，中文按字符
    tokens = set(re.findall(r'[a-z]+|[\u4e00-\u9fff]', text))
    return tokens

def score(item, query_tokens):
    fields = [
        item.get('title', ''),
        ' '.join(item.get('tags', [])),
        item.get('prompts', ['', ''])[1] if len(item.get('prompts', [])) > 1 else '',  # 中文 prompt
        item.get('prompts', [''])[0] if item.get('prompts') else '',  # 英文 prompt
    ]
    text = ' '.join(fields)
    item_tokens = tokenize(text)
    hits = len(query_tokens & item_tokens)
    return hits

def search(query, top_n=3):
    data_path = Path(__file__).parent / 'prompts.json'
    data = json.loads(data_path.read_text())
    items = data['items']

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    scored = [(score(item, query_tokens), item) for item in items]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [(s, item) for s, item in scored if s > 0][:top_n]

    results = []
    for s, item in top:
        en_prompt = item['prompts'][0] if item.get('prompts') else ''
        zh_prompt = item['prompts'][1] if len(item.get('prompts', [])) > 1 else ''
        results.append({
            'title': item['title'],
            'tags': item['tags'],
            'en_prompt': en_prompt,
            'zh_prompt': zh_prompt,
            'score': s,
        })
    return results

if __name__ == '__main__':
    query = sys.argv[1] if len(sys.argv) > 1 else ''
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    results = search(query, top_n)
    if not results:
        print('未找到相关 prompt')
        sys.exit(0)

    for i, r in enumerate(results, 1):
        print(f'【{i}】{r["title"]} | tags: {", ".join(r["tags"])}')
        print(f'英文 prompt:\n{r["en_prompt"]}')
        print()
