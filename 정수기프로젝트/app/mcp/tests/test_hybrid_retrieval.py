"""실제 로컬 Chroma를 사용해 검색 격리·복구·영속성을 검사한다(API는 대체)."""
import json
import pytest
from 정수기프로젝트.app.rag import vector_index as vi
from 정수기프로젝트.app.rag import retriever as rag


class Embeddings:
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        if '실패' in text:
            raise RuntimeError('embedding failed')
        return [1., 0., 0.] if '계약' in text or '약속' in text else [0., 1., 0.]


def chunk(ident, text):
    return {'chunk_id': ident, 'document_id': ident, 'title': '공개 안내', 'section': '일반',
            'content': text, 'interpretation': '일반 참고', 'review_status': 'verified',
            'keywords': [], 'url': 'https://www.lge.co.kr', 'checked_at': '2026-10-15'}


@pytest.fixture
def corpus():
    return [chunk('public-contract', '계약 조건 안내'), chunk('other-model', '필터 안내')]


def test_chroma_persists_and_only_queries_allowed_ids(tmp_path, corpus):
    built = vi.build_index(corpus, tmp_path, Embeddings())
    assert built['status'] == 'ready' and built['passages'] == 2
    assert (tmp_path / 'chroma/chroma.sqlite3').is_file()
    assert vi.status(corpus, tmp_path)['status'] == 'ready'
    assert vi.build_index(corpus, tmp_path, Embeddings())['reused']
    assert vi.semantic_search('약속', corpus, {'public-contract'}, root=tmp_path, embedder=Embeddings())[0][0] == 'public-contract'
    assert vi.semantic_search('약속', corpus, {'other-model'}, root=tmp_path, embedder=Embeddings()) == []


def test_changed_source_or_embedding_model_does_not_use_old_index(tmp_path, corpus, monkeypatch):
    vi.build_index(corpus, tmp_path, Embeddings())
    changed = [{**corpus[0], 'content': '변경된 계약'}, corpus[1]]
    assert vi.status(changed, tmp_path)['code'] == 'INDEX_STALE'
    monkeypatch.setenv('RAG_EMBEDDING_MODEL', 'other-model')
    assert vi.status(corpus, tmp_path)['code'] == 'INDEX_STALE'


def test_failed_rebuild_preserves_active_collection(tmp_path, corpus):
    before = vi.build_index(corpus, tmp_path, Embeddings())
    with pytest.raises(RuntimeError):
        vi.build_index([chunk('bad', '실패')], tmp_path, Embeddings())
    assert json.loads((tmp_path / 'active.json').read_text())['collection'] == before['collection']
    assert vi.status(corpus, tmp_path)['status'] == 'ready'


def test_semantic_match_without_keyword_and_fallback(tmp_path, monkeypatch):
    corpus = [chunk('public-contract', '계약 조건 안내')]
    monkeypatch.setattr(rag, 'documents', lambda: corpus)
    from 정수기프로젝트.app.rag import approved_loader
    monkeypatch.setattr(approved_loader, 'approved_chunks', lambda *args: ([], []))
    monkeypatch.setenv('RAG_VECTOR_PATH', str(tmp_path))
    monkeypatch.setenv('RAG_SEARCH_MODE', 'hybrid')
    monkeypatch.setattr(vi, 'embeddings', Embeddings)
    vi.build_index(corpus, tmp_path, Embeddings())
    result = rag.search_contract_knowledge('약속')
    assert result['retrieval']['mode'] == 'hybrid'
    assert result['documents'][0]['chunk_id'] == 'public-contract'
    result = rag.search_contract_knowledge('실패')
    assert result['retrieval']['mode'] == 'keyword'
    assert result['retrieval']['vector_warning'] == 'RuntimeError'
    assert result['status'] == 'unverified'


def test_index_missing_does_not_break_existing_keyword_search(tmp_path, monkeypatch):
    monkeypatch.setenv('RAG_VECTOR_PATH', str(tmp_path))
    monkeypatch.setenv('RAG_SEARCH_MODE', 'hybrid')
    result = rag.search_contract_knowledge('의무기간 전체기간 차이')
    assert result['status'] == 'ok'
    assert result['retrieval'] == {'mode': 'keyword', 'vector_warning': 'INDEX_NOT_READY'}


def test_vector_results_cannot_override_original_body_or_scope(monkeypatch):
    monkeypatch.setenv('RAG_SEARCH_MODE', 'hybrid')
    monkeypatch.setattr(vi, 'semantic_search', lambda query, corpus, allowed:
                        [('LG-SUB-period', .9)] if 'LG-SUB-period' in allowed else [])
    result = rag.search_contract_knowledge('약속의마지막날', contract_only=True)
    assert result['retrieval']['mode'] == 'hybrid'
    assert result['documents'][0]['content'] == next(c['content'] for c in rag.documents() if c['chunk_id'] == 'LG-SUB-period')


def test_only_verified_public_sources_enter_index():
    corpus = rag.public_corpus()
    assert all(c['review_status'] == 'verified' for c in corpus)
    assert not any('DEMO-U' in c['chunk_id'] or 'session_key' in c for c in corpus)


def test_embedding_windows_keep_original_table_unchanged():
    body = '<table>' + '공개 계약 조건 ' * 800 + '</table>'
    rows = [chunk('public-table', body)]
    parts = list(vi.passages(rows))
    assert len(parts) > 1 and max(len(p[2]) for p in parts) < 1400
    assert rows[0]['content'] == body


def test_reranker_accepts_only_provided_ids_and_preserves_question():
    from types import SimpleNamespace
    from 정수기프로젝트.app.rag.reranker import rerank
    captured=[]
    class Model:
        def with_structured_output(self, *args, **kwargs):return self
        def invoke(self, messages):
            captured.extend(messages)
            return SimpleNamespace(ordered_ids=['invented', 'public-contract', 'public-contract'])
    assert rerank('수리 기사를 기다리고 있어요', [chunk('public-contract','계약 안내')], Model()) == ['public-contract']
    assert '수리 기사를 기다리고 있어요' in captured[1][1]


def test_low_confidence_rerank_filters_model_scope_and_recovers(tmp_path, corpus, monkeypatch):
    from 정수기프로젝트.app.rag import reranker
    class WeakEmbeddings(Embeddings):
        def embed_query(self, text):
            if text=='약속':return [.35, .93675, 0.]
            return super().embed_query(text)
    vi.build_index(corpus, tmp_path, Embeddings())
    monkeypatch.setenv('RAG_RERANK','true')
    received=[]
    def rank(query, rows):
        received.extend(r['chunk_id'] for r in rows)
        return ['public-contract']
    monkeypatch.setattr(reranker,'rerank',rank)
    found=vi.semantic_search('약속',corpus,{'public-contract'},root=tmp_path,embedder=WeakEmbeddings())
    assert found==[('public-contract',1.)]
    assert received==['public-contract']
    monkeypatch.setattr(reranker,'rerank',lambda *args: (_ for _ in ()).throw(TimeoutError()))
    assert vi.semantic_search('약속',corpus,{'public-contract'},root=tmp_path,embedder=WeakEmbeddings())[0][0]=='public-contract'


def test_reviewed_candidates_are_not_overridden_by_generic_keyword_matches():
    ranked=rag.hybrid_ranking([(40,'unrelated'),(5,'relevant')], [('relevant',1.)], {'unrelated'}, reranked=True)
    assert ranked==['relevant']
    assert rag.hybrid_ranking([(40,'unrelated')], [], {'unrelated'}, reranked=True)==[]
