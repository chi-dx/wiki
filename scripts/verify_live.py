"""Explicit live validation; performs billable model queries against the running portal."""
import json
from pathlib import Path
import httpx

root = Path(__file__).resolve().parent.parent
results = []
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=300) as client:
    client.get('/health/ready').raise_for_status()
    catalog = client.get('/api/wiki').json()
    print('Compiler catalog pages:', len(catalog['pages']), flush=True)
    for question, external in [
        ('SVE向量化实验应该覆盖哪些正确性边界？现有资料是否有真实收益数据？', False),
        ('性能测试数据波动大时应先检查什么？请区分团队资料与其他资料。', True),
    ]:
        response = client.post('/api/ask', json={'question':question, 'include_external':external})
        response.raise_for_status()
        result = response.json()
        for evidence in result['evidence']:
            client.get(evidence['url']).raise_for_status()
        feedback = client.post('/api/feedback', json={'request_id':result['request_id'], 'solved':False,
                                                    'reason':'自动联调记录：仅检查链路，不代表人工质量评价'})
        feedback.raise_for_status()
        results.append(result)
        print(json.dumps({'mode':result['mode'],'sources':result['sources'],
                          'references':len(result['evidence']),'elapsed_ms':result['elapsed_ms'],
                          'answer':result['answer']},ensure_ascii=False), flush=True)
output = root / 'data' / 'live-validation.json'
output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print('Saved data/live-validation.json', flush=True)
