"""공개 검수 자료 전용 Chroma 인덱스. 개인 계약·대화·권한은 저장하지 않는다."""
import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

DEFAULT_ROOT = Path(__file__).parents[1] / 'backend/ai/runtime/rag'
SCHEMA = 3


class VectorIndexError(RuntimeError):
    pass


class SemanticRanking(list):
    def __init__(self, items=(), *, reranked=False):
        super().__init__(items)
        self.reranked = reranked


def index_root():
    return Path(os.environ.get('RAG_VECTOR_PATH') or DEFAULT_ROOT).resolve()


def embedding_model():
    return os.environ.get('RAG_EMBEDDING_MODEL', 'text-embedding-3-large').strip()


def embeddings():
    # 대화 모델을 Anthropic으로 바꿔도 문서/질의 임베딩 모델은 같아야 한다.
    from langchain_openai import OpenAIEmbeddings
    # passages가 길이를 제한하므로 실행 중 토크나이저 다운로드를 하지 않는다.
    return OpenAIEmbeddings(model=embedding_model(), request_timeout=15, max_retries=1,
                            check_embedding_ctx_length=False)


def fingerprint(chunks):
    payload = json.dumps({'schema': SCHEMA, 'model': embedding_model(), 'chunks':
                          sorted(chunks, key=lambda row: row['chunk_id'])},
                         sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def passages(chunks):
    """임베딩용 짧은 구간만 구성. 답변에는 분할 전 검수 본문을 반환한다."""
    # 한국어와 큰 표도 임베딩 상한을 지킨다. 원본과 반환할 표는 나누지 않는다.
    for row in chunks:
        body = row['content']
        prefix = row['title'] + '\n' + row.get('section', '') + '\n'
        question = re.search(r'### 질문\s*\n([\s\S]+?)\n### 답변', body)
        if question:
            # 표준답변은 긴 법령 설명보다 고객의 상황이 검색에 잘 반영되게 한다.
            yield row['chunk_id'], 'question', question.group(1).strip()
        for part, start in enumerate(range(0, len(body), 1080)):
            yield row['chunk_id'], part, prefix + body[start:start + 1200]


@lru_cache(maxsize=3)
def client(path):
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))


def _active(root):
    try:
        return json.loads((root / 'active.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise VectorIndexError('INDEX_NOT_READY') from exc


def status(chunks, root=None):
    root = Path(root or index_root())
    try:
        active = _active(root)
        if active.get('fingerprint') != fingerprint(chunks):
            raise VectorIndexError('INDEX_STALE')
        collection = client(str(root / 'chroma')).get_collection(active['collection'], embedding_function=None)
        if collection.count() != active['passages']:
            raise VectorIndexError('INDEX_INCOMPLETE')
        return {'status': 'ready', **active}
    except VectorIndexError as exc:
        return {'status': 'unavailable', 'code': str(exc)}
    except Exception:
        return {'status': 'unavailable', 'code': 'INDEX_UNAVAILABLE'}


def build_index(chunks, root=None, embedder=None):
    """별도 컬렉션 구축 완료 후 전환. 실패하면 현재 인덱스를 유지한다."""
    root = Path(root or index_root())
    root.mkdir(parents=True, exist_ok=True)
    current = status(chunks, root)
    if current['status'] == 'ready':
        return {**current, 'reused': True}
    rows = list(passages(chunks))
    if not rows:
        raise VectorIndexError('EMPTY_CORPUS')
    name = 'public_' + fingerprint(chunks)[:20] + '_' + uuid4().hex[:8]
    db = client(str(root / 'chroma'))
    collection = db.create_collection(name, embedding_function=None, metadata={'hnsw:space': 'cosine'})
    embedder = embedder or embeddings()
    try:
        for start in range(0, len(rows), 48):
            batch = rows[start:start + 48]
            texts = [text for _, _, text in batch]
            vectors = embedder.embed_documents(texts)
            collection.add(ids=[f'{ident}:{part}' for ident, part, _ in batch],
                           documents=texts, embeddings=vectors,
                           metadatas=[{'chunk_id': ident} for ident, _, _ in batch])
        active = {'schema': SCHEMA, 'fingerprint': fingerprint(chunks), 'model': embedding_model(),
                  'collection': name, 'chunks': len(chunks), 'passages': len(rows)}
        temporary = root / ('active-' + uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(active, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, root / 'active.json')
        return {'status': 'ready', **active, 'reused': False}
    except Exception:
        db.delete_collection(name)
        raise


def semantic_search(query, corpus, allowed, *, root=None, embedder=None):
    """허용된 청크만 DB 단계에서 검색하고 원본 허용 목록으로 다시 확인한다."""
    root = Path(root or index_root())
    current = status(corpus, root)
    if current['status'] != 'ready':
        raise VectorIndexError(current['code'])
    if not allowed:
        return []
    collection = client(str(root / 'chroma')).get_collection(current['collection'], embedding_function=None)
    query_vector = (embedder or embeddings()).embed_query(query)
    def search(vector):
        return collection.query(query_embeddings=[vector], n_results=min(40, current['passages']),
                                where={'chunk_id': {'$in': sorted(allowed)}}, include=['metadatas', 'distances'])
    result = search(query_vector)
    # 유사도가 낮으면 실제 후보의 질문·사건을 비교한다. 재표현한 질의를
    # 원 질문보다 우선하지 않으며, 실패하면 원래 벡터 순위를 보존한다.
    confidence = max((1 - float(d) for d in result['distances'][0]), default=0)
    distinct = {}
    for metadata, distance in zip(result['metadatas'][0], result['distances'][0]):
        ident = metadata['chunk_id']
        distinct[ident] = max(distinct.get(ident, -1), 1-float(distance))
    leading = sorted(distinct.values(), reverse=True)
    close_candidates = len(leading)>1 and leading[0]-leading[1]<.04
    if (confidence < .40 or close_candidates) and os.environ.get('RAG_RERANK', 'true').lower() == 'true':
        try:
            from .reranker import rerank
            by_id = {row['chunk_id']: row for row in corpus if row['chunk_id'] in allowed}
            ids = list(dict.fromkeys(m['chunk_id'] for m in result['metadatas'][0] if m['chunk_id'] in by_id))[:24]
            selected = rerank(query, [by_id[ident] for ident in ids])
            return SemanticRanking([(ident, 1 - rank * .04) for rank, ident in enumerate(selected)], reranked=True)
        except Exception:
            pass
    best = {}
    threshold = float(os.environ.get('RAG_MIN_SIMILARITY', '0.30'))
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise VectorIndexError('INVALID_SIMILARITY_THRESHOLD')
    for metadata, distance in zip(result['metadatas'][0], result['distances'][0]):
        ident = metadata['chunk_id']
        similarity = 1 - float(distance)
        if ident in allowed and math.isfinite(similarity) and similarity >= threshold:
            best[ident] = max(best.get(ident, -1), similarity)
    return SemanticRanking(sorted(best.items(), key=lambda row: (-row[1], row[0]))[:12])
