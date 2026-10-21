"""Поиск похожих фраз. Его оценка не подтверждает опыт."""
import hashlib
import importlib.metadata
import json
import math
from collections import Counter

from data import normalize

MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
REPO = 'Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q'
REVISION = 'faf4aa4225822f3bc6376869cb1164e8e3feedd0'


def grams(text):
    text = ' ' + normalize(text) + ' '
    return Counter(text[i:i+n] for n in (3, 4, 5) for i in range(len(text)-n+1))


def lexical_scores(rows, query):
    phrases = sorted({normalize(p) for r in rows for p in r['domains']})
    counts = {p: grams(p) for p in phrases}
    df = Counter(term for c in counts.values() for term in c)
    def vector(counts):
        values = {term: (1+math.log(n)) * (1+math.log((len(phrases)+1)/(df.get(term, 0)+1)))
                  for term, n in counts.items()}
        length = math.sqrt(sum(v*v for v in values.values())) or 1
        return {term: v/length for term, v in values.items()}
    q = vector(grams(query))
    scores = {p: sum(value*q.get(term, 0) for term, value in vector(c).items()) for p, c in counts.items()}
    return {r['id']: max((scores[normalize(p)] for p in r['domains']), default=0) for r in rows}


class Embeddings:
    def __init__(self, rows, queries, cache):
        import numpy as np
        from fastembed import TextEmbedding
        from huggingface_hub import snapshot_download
        self.np, self.rows = np, rows
        self.phrases = sorted({normalize(p) for r in rows for p in r['domains']})
        self.positions = {p: i for i, p in enumerate(self.phrases)}
        self.queries = sorted(set(queries))
        snapshot = cache / 'models' / ('models--'+REPO.replace('/', '--')) / 'snapshots' / REVISION
        if not (snapshot/'model_optimized.onnx').exists():
            snapshot = snapshot_download(repo_id=REPO, revision=REVISION, cache_dir=str(cache/'models'),
                allow_patterns=['model_optimized.onnx', 'config.json', 'tokenizer.json',
                                'tokenizer_config.json', 'special_tokens_map.json'])
        from pathlib import Path
        snapshot = Path(snapshot)
        digest = hashlib.sha256((snapshot/'model_optimized.onnx').read_bytes()).hexdigest()
        versions = {p: importlib.metadata.version(p) for p in ('fastembed', 'onnxruntime', 'numpy')}
        key = hashlib.sha256(json.dumps([REVISION, digest, versions, self.phrases, self.queries],
                                        ensure_ascii=False).encode()).hexdigest()
        cache.mkdir(parents=True, exist_ok=True)
        path = cache/(key+'.npz')
        self.info = {'model': MODEL, 'repository': REPO, 'revision': REVISION,
                     'weights_sha256': digest, 'packages': versions, 'cache_hit': path.exists(),
                     'device': 'CPU', 'dimensions': 384, 'limit_tokens': 128}
        if path.exists():
            with np.load(path, allow_pickle=False) as saved:
                self.vectors, self.query_vectors = saved['phrases'], saved['queries']
        else:
            model = TextEmbedding(model_name=MODEL, specific_model_path=str(snapshot), threads=2,
                                  providers=['CPUExecutionProvider'])
            self.vectors = np.asarray(list(model.passage_embed(self.phrases, batch_size=16)), dtype=np.float32)
            self.query_vectors = np.asarray(list(model.query_embed(self.queries, batch_size=16)), dtype=np.float32)
            np.savez_compressed(path, phrases=self.vectors, queries=self.query_vectors)
        self.vectors /= np.maximum(np.linalg.norm(self.vectors, axis=1, keepdims=True), 1e-12)
        self.query_vectors /= np.maximum(np.linalg.norm(self.query_vectors, axis=1, keepdims=True), 1e-12)

    def scores(self, query):
        sims = self.vectors @ self.query_vectors[self.queries.index(query)]
        return {r['id']: max((float(sims[self.positions[normalize(p)]]) for p in r['domains']), default=0)
                for r in self.rows}
