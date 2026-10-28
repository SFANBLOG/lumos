"""
BM25 全文检索索引 (混合检索的关键词通道).

对法条语料做 jieba 中文分词后构建 BM25Okapi 倒排索引, 提供关键词
词频召回, 与 Milvus 向量通道经 RRF 融合为混合检索结果。
零分 (未命中查询词) 文档不进入候选池, 避免无关键词重叠的条文
给 RRF 融合引入噪声。语料为 14 部劳动法律法规完整条文 (约 660 条),
索引驻留内存, 检索成本可忽略。
"""

from __future__ import annotations

from functools import lru_cache

from loguru import logger

from app.rag.law_corpus import ALL_LAWS

__all__ = ["bm25_search_laws", "get_bm25_index", "zh_tokenize"]

#: jieba 领域词典 (劳动法常用术语), 避免领域词被拆散导致 BM25 失配
_DOMAIN_LEXICON = [
    "竞业限制", "违约金", "经济补偿", "赔偿金", "劳动报酬", "加班费", "加班工资",
    "试用期", "试用期工资", "社会保险", "劳动合同", "劳动争议", "劳动仲裁",
    "仲裁委员会", "仲裁管辖", "解除劳动合同", "终止劳动合同", "服务期",
    "培训服务期", "专项培训", "培训费", "劳务派遣", "无固定期限劳动合同",
    "年休假", "带薪年休假", "婚丧假", "法定节假日", "规章制度", "工作时间",
    "休息休假", "岗位职责", "工作内容", "离职审批", "离职手续", "克扣工资",
    "拖欠工资", "如实告知", "用人单位", "竞业限制补偿",
    "医疗期", "病假工资", "停工留薪期", "同工同酬", "格式条款",
    "就业歧视", "童工", "仲裁时效", "先予执行", "终局裁决",
    "支付令", "举证责任", "视同工伤", "产假", "生育津贴",
    "劳务派遣用工", "假外包真派遣", "最低工资标准", "滞纳金",
]

_LEXICON_LOADED = False


def _register_domain_lexicon() -> None:
    """向 jieba 注册劳动法领域词 (幂等, 进程内仅执行一次)."""
    global _LEXICON_LOADED
    if _LEXICON_LOADED:
        return
    import jieba

    for word in _DOMAIN_LEXICON:
        jieba.add_word(word)
    _LEXICON_LOADED = True


def zh_tokenize(text: str) -> list[str]:
    """中文分词，并保留复合查询中包含的领域短语。

    例如 jieba 可能把“竞业限制补偿”视为一个词，但法条语料通常分别
    标注“竞业限制”“经济补偿”。同时保留两种粒度，避免 BM25 漏召回。
    """
    import jieba

    tokens = [t.strip() for t in jieba.lcut(text) if t.strip()]
    for term in _DOMAIN_LEXICON:
        if term in text and term not in tokens:
            tokens.append(term)
    return tokens


_register_domain_lexicon()  # 模块导入即注册, 保证索引与查询同一分词口径


def _law_doc_text(law: dict) -> str:
    """法条检索文档文本 (与向量化文本保持一致)."""
    keywords = ", ".join(law.get("keywords", []))
    return f"{law['law_name']} {law['article']} {law['content']} {keywords}"


class BM25Index:
    """法条语料 BM25 索引 (rank_bm25 封装)."""

    def __init__(self, laws: list[dict]) -> None:
        raw_docs = [_law_doc_text(l) for l in laws]
        self._laws = laws

        from rank_bm25 import BM25Okapi

        try:
            # 新版 rank_bm25: 索引构建时注入分词器, query 仍须传 token 序列
            self._bm25 = BM25Okapi(raw_docs, tokenizer=zh_tokenize)
        except TypeError:
            # 旧版 (<0.2.2) 无 tokenizer 参数: 预分词后传入
            self._bm25 = BM25Okapi([zh_tokenize(d) for d in raw_docs])

    def __len__(self) -> int:
        """索引中的文档数 (与语料条数一致)."""
        return len(self._laws)

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[dict]:
        """
        BM25 检索, 返回与向量通道同构的命中列表 (按分数降序).

        查询一律先经 zh_tokenize 切成 token 序列再打分 (与索引分词口径
        一致; rank_bm25 不会对 query 自动分词)。
        零分文档 (未命中任何查询词) 不进入候选: 否则会以 rank 形式
        混入 RRF 融合, 稀释真实相关命的排序与相关度分数。
        """
        scores = self._bm25.get_scores(zh_tokenize(query))

        ranked = sorted(
            enumerate(scores),
            key=lambda pair: pair[1],
            reverse=True,
        )
        hits: list[dict] = []
        for idx, score in ranked:
            if score <= 0:
                break  # 降序排列, 后续均为零分
            law = self._laws[idx]
            if category and law.get("category") != category:
                continue
            hits.append({
                "law_name": law["law_name"],
                "article": law["article"],
                "content": law["content"],
                "keywords": ", ".join(law.get("keywords", [])),
                "category": law.get("category", ""),
                "score": round(float(score), 4),
            })
            if len(hits) >= top_k:
                break
        return hits


@lru_cache
def get_bm25_index() -> BM25Index:
    """全局 BM25 索引单例."""
    index = BM25Index(ALL_LAWS)
    logger.info(f"🔎 BM25 索引就绪 | 语料: {len(ALL_LAWS)} 条条文")
    return index


def bm25_search_laws(
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
    """BM25 关键词通道检索入口."""
    return get_bm25_index().search(query, top_k=top_k, category=category)
