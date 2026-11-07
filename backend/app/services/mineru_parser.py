"""
MinerU 版面解析适配层 (PDF → Markdown + 结构化块).

把复杂版面的合同 PDF 交给 MinerU (OpenDataLab) 做版面检测、阅读顺序还原、
表格/公式识别与 OCR，产出 Markdown 与 content_list 结构化块，再交给上游
「文本抽取 → 混合检索 RAG → LangGraph 多 Agent 审查」链路。

设计约束 (与项目其它降级链路保持一致):

1. **可插拔**: MinerU 是可选能力，不装 CLI、不配服务、调用失败都不影响服务启动，
   ``PDF_PARSER_STRATEGY=legacy`` 可一键回到内置 pypdf/PyMuPDF/OCR 链路；
2. **不静默**: 失败原因写入 ``ParseMeta.fallback_reason`` 并随 ingest 响应下发；
   ``auto`` 策略显式回退并记日志，``mineru`` 策略 fail-loud (抛 503)，
   避免「看起来解析成功、实际是空文本」的假阴性；
3. **本地优先**: 默认走本机 CLI 或内网自建解析服务，绝不把合同上传到公网解析服务；
4. **多模态联动**: MinerU 版面切出的图片块 (公章/签名/手写批注/图表截图) 可交给
   多模态视觉大模型 (qwen-vl 等) 补识，识别文本回填到原图片位置。

支持两种后端 (``MINERU_BACKEND``):

- ``cli``  : 本机调用 ``mineru-kit parse`` (MinerU 4.x) 或 ``mineru -p`` (2.x/3.x)；
- ``http`` : 调用内网自建 MinerU 解析服务 (``scripts/mineru_http_server.py``)，
             也可对接任何返回 Markdown / content_list JSON 的解析服务。
"""

from __future__ import annotations

import base64
import html as html_lib
import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# 版面图片块专用提示词: 与整页 OCR 的通用提示词区分开
VISION_IMAGE_PROMPT = (
    "这是劳动合同文档中的一个图片区块（可能是公章、签名、手写批注、表格截图或证照）。"
    "请提取其中全部可见文字，并简述图片内容；只输出内容本身，不要解释过程。"
)

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


class MinerUUnavailable(RuntimeError):
    """MinerU 不可用或解析失败；携带原因，由上层决定回退还是 fail-loud."""


@dataclass
class MinerUBlock:
    """MinerU content_list 归一化后的版面块."""

    type: str  # text | title | table | image | equation | ...
    text: str = ""
    page_idx: int | None = None
    image_path: str | None = None


@dataclass
class MinerUResult:
    """一次 MinerU 解析的统一结果."""

    text: str
    engine: str  # mineru:cli:v4 | mineru:cli:v2 | mineru:http
    blocks: list[MinerUBlock] = field(default_factory=list)
    # (原始引用, 图片字节)；字节在临时目录清理前读入内存，便于后续视觉识别
    images: list[tuple[str, bytes]] = field(default_factory=list)
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)
    vision_enriched: int = 0


@dataclass
class ParseMeta:
    """随 /ingest/file 下发的解析链路元信息 (前端可展示「由谁解析的」)."""

    parser: str = "legacy"  # mineru | legacy
    detail: str = ""  # 具体引擎/链路
    blocks: int = 0
    images: int = 0
    vision_enriched: int = 0
    fallback_reason: str = ""  # auto 策略回退原因，空表示未回退

    def to_dict(self) -> dict[str, object]:
        return {
            "parser": self.parser,
            "detail": self.detail,
            "blocks": self.blocks,
            "images": self.images,
            "vision_enriched": self.vision_enriched,
            "fallback_reason": self.fallback_reason,
        }


def result_to_meta(result: MinerUResult) -> ParseMeta:
    return ParseMeta(
        parser="mineru",
        detail=result.engine,
        blocks=len(result.blocks),
        images=len(result.images),
        vision_enriched=result.vision_enriched,
    )


def fallback_meta(reason: str = "") -> ParseMeta:
    return ParseMeta(
        parser="legacy",
        detail="pypdf + pymupdf + OCR (内置逐页混合抽取)",
        fallback_reason=reason,
    )


# ─── 入口 ──────────────────────────────────────────────────────


def parse_pdf(data: bytes, settings: Settings | None = None) -> MinerUResult:
    """解析 PDF；不可用时抛 MinerUUnavailable (由 text_extractor 决定回退/503)."""
    s = settings or get_settings()
    backend = _resolve_backend(s)
    if backend == "cli":
        result = _parse_cli(data, s)
    elif backend == "http":
        result = _parse_http(data, s)
    else:
        raise MinerUUnavailable("未找到 MinerU CLI (mineru-kit/mineru)，且未配置 MINERU_HTTP_URL")

    if not result.text.strip() and not result.blocks:
        raise MinerUUnavailable("MinerU 未产出任何文本 (输出为空)")

    logger.info(
        "MinerU parsed PDF: engine=%s blocks=%s images=%s chars=%s",
        result.engine,
        len(result.blocks),
        len(result.images),
        len(result.text),
    )
    return result


def _resolve_backend(s: Settings) -> str:
    configured = str(getattr(s, "mineru_backend", "auto") or "auto").lower()
    if configured in ("cli", "http"):
        return configured
    if _resolve_cli(s) is not None:
        return "cli"  # 本地 CLI 优先，避免合同出内网
    if str(getattr(s, "mineru_http_url", "") or "").strip():
        return "http"
    return "none"


# ─── CLI 后端 ──────────────────────────────────────────────────


def _resolve_cli(s: Settings) -> tuple[str, str] | None:
    """返回 (可执行文件路径, 版本风味 v4|v2)；找不到返回 None."""
    explicit = str(getattr(s, "mineru_cli", "") or "").strip()
    flavor = str(getattr(s, "mineru_cli_flavor", "auto") or "auto").lower()
    if explicit:
        if flavor == "auto":
            flavor = "v4" if "kit" in Path(explicit).name.lower() else "v2"
        found = explicit if Path(explicit).is_file() else shutil.which(explicit)
        return (found, flavor) if found else None

    for cmd, candidate_flavor in (("mineru-kit", "v4"), ("mineru", "v2")):
        found = shutil.which(cmd)
        if found:
            return found, candidate_flavor
    return None


def _build_command(
    cli: str,
    flavor: str,
    src: Path,
    work: Path,
    s: Settings,
) -> tuple[list[str], Path]:
    """按 MinerU 版本拼命令，返回 (argv, 主输出路径/目录)."""
    tier = str(getattr(s, "mineru_tier", "standard") or "standard")
    if flavor == "v4":
        # mineru-kit parse <in> -o <out.md> --tier standard (默认全页)
        out = work / "result.md"
        cmd = [cli, "parse", str(src), "-o", str(out), "--tier", tier]
        # mineru parse 默认只解析前 10 页；显式要求全页，合同不能漏页
        if "kit" not in Path(cli).name.lower():
            cmd += ["--pages", "all"]
        return cmd, out

    # MinerU 2.x/3.x: mineru -p <in> -o <outdir> -m auto
    out = work / "mineru_out"
    out.mkdir(parents=True, exist_ok=True)
    method = str(getattr(s, "mineru_method", "auto") or "auto")
    return [cli, "-p", str(src), "-o", str(out), "-m", method], out


def _parse_cli(data: bytes, s: Settings) -> MinerUResult:
    resolved = _resolve_cli(s)
    if resolved is None:
        raise MinerUUnavailable("未找到 MinerU CLI (mineru-kit / mineru)")
    cli, flavor = resolved
    timeout = max(1, int(getattr(s, "mineru_timeout_seconds", 180) or 180))

    with tempfile.TemporaryDirectory(prefix="lumos-mineru-") as tmp:
        work = Path(tmp)
        src = work / "input.pdf"
        src.write_bytes(data)
        cmd, primary = _build_command(cli, flavor, src, work, s)

        logger.debug("MinerU CLI: %s", " ".join(cmd))
        try:
            proc = subprocess.run(  # noqa: S603  (命令由受控配置拼接，非 shell)
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise MinerUUnavailable(f"MinerU 解析超时 ({timeout}s)") from e
        except OSError as e:
            raise MinerUUnavailable(f"MinerU CLI 启动失败: {e}") from e

        if proc.returncode != 0:
            raise MinerUUnavailable(
                f"MinerU CLI 退出码 {proc.returncode}: {_tail(proc.stderr or proc.stdout)}"
            )

        markdown, blocks, refs = _collect_outputs(work, primary)
        images = _load_images(work, refs)  # 必须在 TemporaryDirectory 清理前读进内存

    text = markdown.strip() or _blocks_to_text(blocks)
    return MinerUResult(
        text=text,
        engine=f"mineru:cli:{flavor}",
        blocks=blocks,
        images=images,
        page_count=_count_pages(blocks),
    )


def _collect_outputs(
    work: Path, primary: Path
) -> tuple[str, list[MinerUBlock], list[str]]:
    """收集 MinerU 产物: Markdown、content_list 结构化块、图片引用."""
    md_files: list[Path] = []
    if primary.is_file():
        md_files = [primary]
    elif primary.is_dir():
        md_files = sorted(primary.rglob("*.md"))
    if not md_files:
        md_files = sorted(work.rglob("*.md"))
    markdown = "\n\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in md_files
    )

    cl_files = sorted(work.rglob("*content_list*.json"))
    blocks: list[MinerUBlock] = []
    if cl_files:
        try:
            blocks = _parse_content_list(json.loads(cl_files[0].read_text(encoding="utf-8")))
        except (ValueError, OSError) as e:
            logger.warning("MinerU content_list 解析失败，回退 Markdown 分块: %s", e)
    if not blocks:
        blocks = _blocks_from_markdown(markdown)

    refs: list[str] = []
    for block in blocks:
        if block.type == "image" and block.image_path:
            refs.append(block.image_path)
    refs.extend(m.group(2) for m in _MD_IMAGE_RE.finditer(markdown))
    return markdown, blocks, _dedupe(refs)


def _load_images(work: Path, refs: list[str]) -> list[tuple[str, bytes]]:
    """把图片引用解析为磁盘文件并读入内存 (越界/缺失的图片直接跳过)."""
    loaded: list[tuple[str, bytes]] = []
    for ref in refs:
        path = _resolve_image(work, ref)
        if not path:
            continue
        try:
            loaded.append((ref, path.read_bytes()))
        except OSError as e:
            logger.warning("MinerU 图片读取失败 %s: %s", ref, e)
    return loaded


def _resolve_image(work: Path, ref: str) -> Path | None:
    """MinerU 输出的 img_path 可能是相对路径/带查询串/只给文件名."""
    clean = ref.split("?", 1)[0].split("#", 1)[0].strip()
    if clean.startswith("data:"):
        return None  # 内联 base64 由 HTTP 后端处理
    p = Path(clean)
    if p.is_absolute() and p.is_file():
        return p
    for base in (work, work / "mineru_out", work / "images"):
        candidate = base / clean
        if candidate.is_file():
            return candidate
    if p.name:
        for candidate in work.rglob(p.name):
            if candidate.is_file():
                return candidate
    return None


# ─── HTTP 后端 (内网自建 MinerU 解析服务) ───────────────────────


def _parse_http(data: bytes, s: Settings) -> MinerUResult:
    url = str(getattr(s, "mineru_http_url", "") or "").strip()
    if not url:
        raise MinerUUnavailable("未配置 MINERU_HTTP_URL")
    try:
        import httpx
    except ImportError as e:  # pragma: no cover - 主依赖缺失
        raise MinerUUnavailable("httpx 未安装，无法调用 MinerU HTTP 服务") from e
    timeout = float(getattr(s, "mineru_timeout_seconds", 180) or 180)
    headers: dict[str, str] = {}
    token = str(getattr(s, "mineru_http_token", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = httpx.post(
            url,
            files={"file": ("contract.pdf", data, "application/pdf")},
            data={
                "tier": str(getattr(s, "mineru_tier", "standard") or "standard"),
                "return_content_list": "true",
            },
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise MinerUUnavailable(f"MinerU HTTP 服务不可用: {e}") from e

    content_type = resp.headers.get("content-type", "").lower()
    if "json" in content_type or resp.text.lstrip().startswith(("{", "[")):
        try:
            body = resp.json()
        except ValueError as e:
            raise MinerUUnavailable("MinerU HTTP 返回非法 JSON") from e
        markdown, blocks, images = _from_json(body)
    else:
        # 兼容直接返回 Markdown 文本的解析服务
        markdown, blocks, images = resp.text, _blocks_from_markdown(resp.text), []

    text = markdown.strip() or _blocks_to_text(blocks)
    return MinerUResult(
        text=text,
        engine="mineru:http",
        blocks=blocks,
        images=images,
        page_count=_count_pages(blocks),
    )


def _from_json(body: Any) -> tuple[str, list[MinerUBlock], list[tuple[str, bytes]]]:
    """宽容解析 HTTP 响应: markdown/content/result + content_list + images(base64)."""
    markdown = ""
    content_list: Any = None
    images: list[tuple[str, bytes]] = []

    if isinstance(body, dict):
        for key in ("markdown", "md", "content", "text", "result"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                markdown = value
                break
        for key in ("content_list", "blocks", "data"):
            if key in body:
                content_list = body[key]
                break
        raw_images = body.get("images")
        if isinstance(raw_images, dict):
            for ref, encoded in raw_images.items():
                try:
                    images.append((str(ref), base64.b64decode(str(encoded))))
                except (ValueError, TypeError):
                    continue
    elif isinstance(body, list):
        content_list = body
    elif isinstance(body, str):
        markdown = body

    blocks = _parse_content_list(content_list) if content_list else _blocks_from_markdown(markdown)
    refs = [b.image_path for b in blocks if b.type == "image" and b.image_path]
    refs.extend(m.group(2) for m in _MD_IMAGE_RE.finditer(markdown))
    known = {ref for ref, _ in images}
    for ref in _dedupe(refs):
        if ref not in known and ref.startswith("data:image/") and "," in ref:
            try:
                images.append((ref, base64.b64decode(ref.split(",", 1)[1])))
            except (ValueError, TypeError):
                pass
    return markdown, blocks, images


# ─── content_list / Markdown 归一化 ────────────────────────────


def _parse_content_list(payload: Any) -> list[MinerUBlock]:
    """兼容 MinerU 2.x/3.x content_list.json 与 4.x Content List V1/V2 的字段差异."""
    if isinstance(payload, dict):
        for key in ("content_list", "data", "result", "content", "blocks"):
            if key in payload:
                return _parse_content_list(payload[key])
        return []
    if not isinstance(payload, list):
        return []

    blocks: list[MinerUBlock] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        btype = str(item.get("type") or "text").lower()
        page = _as_page(item.get("page_idx"))
        caption = _as_text(
            item.get("image_caption")
            or item.get("table_caption")
            or item.get("caption")
            or ""
        )

        if btype in ("image", "figure", "chart"):
            path = _as_text(item.get("img_path") or item.get("image_path") or "")
            blocks.append(MinerUBlock("image", caption, page, path or None))
            continue
        if btype in ("table", "table_body"):
            body = _as_text(item.get("table_body") or item.get("text") or "")
            text = _html_table_to_text(body) if "<" in body else body
            blocks.append(MinerUBlock("table", f"{caption}\n{text}".strip() if caption else text, page))
            continue
        if btype in ("equation", "interline_equation", "formula"):
            text = _as_text(item.get("latex") or item.get("text") or "")
            blocks.append(MinerUBlock("equation", text, page))
            continue

        text = _as_text(item.get("text") or item.get("content") or "")
        if text:
            blocks.append(MinerUBlock("title" if btype == "title" else "text", text, page))
    return blocks


def _blocks_from_markdown(markdown: str) -> list[MinerUBlock]:
    """没有 content_list 时，按空行 / 图片引用把 Markdown 切成粗粒度块."""
    blocks: list[MinerUBlock] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            kind = "table" if any("|" in line for line in buf) else "text"
            blocks.append(MinerUBlock(kind, "\n".join(buf)))
            buf.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        match = _MD_IMAGE_RE.match(stripped)
        if match:
            flush()
            blocks.append(MinerUBlock("image", match.group(1), None, match.group(2)))
            continue
        if not stripped:
            flush()
            continue
        buf.append(stripped)
    flush()
    return blocks


def _blocks_to_text(blocks: list[MinerUBlock]) -> str:
    return "\n\n".join(b.text.strip() for b in blocks if b.text.strip())


def _html_table_to_text(raw: str) -> str:
    """MinerU 表格常给 HTML 片段，转成「单元格 | 单元格」的纯文本行."""
    text = re.sub(r"(?i)</\s*tr\s*>", "\n", raw)
    text = re.sub(r"(?i)</\s*(td|th)\s*>", " | ", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html_lib.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"\s*\|\s*$", "", line.strip()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        return _as_text(value.get("text") or value.get("content") or "")
    return "" if value is None else str(value)


def _as_page(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _count_pages(blocks: list[MinerUBlock]) -> int:
    pages = [b.page_idx for b in blocks if b.page_idx is not None]
    return max(pages) + 1 if pages else 0


# ─── 多模态视觉模型补识图片块 ──────────────────────────────────


def enrich_with_vision(
    result: MinerUResult,
    settings: Settings | None = None,
    vision_fn: Callable[[bytes], str] | None = None,
) -> int:
    """把版面图片块交给多模态视觉大模型识别，文本回填到 Markdown 原位置.

    失败只记 warning、不影响 MinerU 主文本 (版面解析与视觉增强解耦)；
    返回成功识别的图片块数量。
    """
    s = settings or get_settings()
    enabled = bool(getattr(s, "mineru_vision_enrich", True))
    if not enabled or not result.images:
        _strip_image_refs(result)
        return 0

    if vision_fn is None:
        from app.services.text_extractor import extract_image_via_llm

        def vision_fn(payload: bytes) -> str:  # type: ignore[misc]
            return extract_image_via_llm(payload, prompt=VISION_IMAGE_PROMPT)[0]

    limit = max(0, int(getattr(s, "mineru_vision_max_images", 6) or 0))
    enriched = 0
    for ref, payload in result.images[:limit]:
        if not payload:
            continue
        try:
            recognized = vision_fn(payload)
            if isinstance(recognized, tuple):  # 兼容返回 (text, bool) 的抽取函数
                recognized = recognized[0]
        except Exception as e:  # 视觉模型不可用/超时: 保留版面文本，不拖垮解析
            result.warnings.append(f"{ref}: {type(e).__name__}: {e}")
            logger.warning("MinerU 图片块视觉识别失败 %s: %s", ref, e)
            continue
        if recognized and str(recognized).strip():
            result.text = _replace_image_ref(result.text, ref, str(recognized).strip())
            enriched += 1

    _strip_image_refs(result)
    result.vision_enriched = enriched
    return enriched


def _replace_image_ref(text: str, ref: str, recognized: str) -> str:
    pattern = re.compile(r"!\[[^\]]*\]\(" + re.escape(ref) + r"(\s+\"[^\"]*\")?\)")
    replacement = f"\n【图片内容·多模态识别】\n{recognized}\n"
    new_text, count = pattern.subn(lambda _m: replacement, text, count=1)
    if count:
        return new_text
    return f"{text}\n\n【图片内容·多模态识别（{ref}）】\n{recognized}"


def _strip_image_refs(result: MinerUResult) -> None:
    """清掉临时目录里的相对图片引用，避免下游 LLM 看到失效路径."""

    def _sub(match: re.Match[str]) -> str:
        alt = match.group(1).strip()
        return f"【图片区块：{alt}】" if alt else "【图片区块】"

    result.text = _MD_IMAGE_RE.sub(_sub, result.text)


# ─── 小工具 ────────────────────────────────────────────────────


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _tail(text: str, limit: int = 400) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[-limit:] if cleaned else "(无输出)"
