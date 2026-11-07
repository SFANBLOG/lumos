#!/usr/bin/env python3
"""
内网 MinerU 解析服务 (零第三方依赖, 标准库实现).

把本机 MinerU CLI 包装成 HTTP 端点，供 Lumos backend 通过
``MINERU_BACKEND=http`` + ``MINERU_HTTP_URL`` 调用。适用于:
  - backend 容器里不方便安装 MinerU 模型权重，把解析放在独立 CPU/GPU 节点;
  - 多台 backend 共享同一个解析服务，避免重复下载模型。

启动::

    python scripts/mineru_http_server.py --cli mineru-kit --port 8100
    python scripts/mineru_http_server.py --cli mineru --flavor v2 --port 8100 --token mytoken

对应 backend 配置::

    MINERU_BACKEND=http
    MINERU_HTTP_URL=http://127.0.0.1:8100/v1/file_parse
    MINERU_HTTP_TOKEN=mytoken

协议::

    POST /v1/file_parse
      multipart/form-data: file=<PDF>, tier=standard   (或 JSON: {"file": "<base64>"})
      -> 200 {"markdown": "...", "content_list": [...], "images": {"images/a.jpg": "<base64>"}}
      -> 4xx/5xx {"error": "..."}
    GET /health -> {"status": "ok", "cli": "...", "flavor": "..."}

隐私: 服务只监听显式指定的地址 (默认 127.0.0.1)，不向任何公网服务转发合同。
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import subprocess
import tempfile
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mineru_http_server")

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_MAX_IMAGE_BYTES = 2 * 1024 * 1024
_MAX_IMAGES = 20


class MinerUHandler(BaseHTTPRequestHandler):
    """请求处理器；运行参数由 main() 注入为类属性."""

    cli: str = "mineru-kit"
    flavor: str = "v4"
    tier: str = "standard"
    timeout: int = 180
    token: str = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        logger.info("%s %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler 约定)
        if urlparse(self.path).path == "/health":
            self._json(200, {"status": "ok", "cli": self.cli, "flavor": self.flavor})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path not in ("/v1/file_parse", "/parse"):
            self._json(404, {"error": "not found"})
            return
        if self.token:
            expected = f"Bearer {self.token}"
            if self.headers.get("Authorization", "") != expected:
                self._json(401, {"error": "unauthorized"})
                return

        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 100 * 1024 * 1024:
            self._json(400, {"error": "invalid Content-Length"})
            return

        body = self.rfile.read(length)
        try:
            file_bytes, tier, filename = _parse_request(
                self.headers.get("Content-Type", ""), body
            )
        except Exception as e:  # multipart/JSON 格式错误一律 400
            self._json(400, {"error": f"请求解析失败: {e}"})
            return
        if not file_bytes:
            self._json(400, {"error": "缺少 file 字段"})
            return
        if not file_bytes.lstrip().startswith(b"%PDF"):
            self._json(400, {"error": "file 不是 PDF (magic bytes 不匹配)"})
            return

        try:
            payload = _run_mineru(
                data=file_bytes,
                cli=self.cli,
                flavor=self.flavor,
                tier=tier or self.tier,
                timeout=self.timeout,
                filename=filename,
            )
        except subprocess.TimeoutExpired:
            self._json(504, {"error": "MinerU 解析超时"})
            return
        except Exception as e:
            logger.exception("MinerU 解析失败")
            self._json(500, {"error": f"MinerU 解析失败: {e}"})
            return
        self._json(200, payload)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _parse_request(content_type: str, body: bytes) -> tuple[bytes, str, str]:
    """解析 multipart/form-data，也兼容 JSON + base64 的调用方式."""
    if "multipart/form-data" not in content_type.lower():
        data = json.loads(body.decode("utf-8"))
        return (
            base64.b64decode(data.get("file", "")),
            str(data.get("tier", "")),
            str(data.get("filename", "contract.pdf")),
        )

    # 交给标准库 email 解析器处理 multipart，避免依赖已在 3.13 移除的 cgi 模块
    raw = (
        b"Content-Type: "
        + content_type.encode("utf-8", "replace")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    message = BytesParser(policy=default).parsebytes(raw)
    file_bytes = b""
    tier = ""
    filename = "contract.pdf"
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition") or ""
        payload = part.get_payload(decode=True) or b""
        if name == "file":
            file_bytes = payload
            filename = part.get_filename() or filename
        elif name == "tier":
            tier = payload.decode("utf-8", "replace").strip()
    return file_bytes, tier, filename


def _build_command(cli: str, flavor: str, src: Path, work: Path, tier: str) -> tuple[list[str], Path]:
    if flavor == "v4":
        out = work / "result.md"
        cmd = [cli, "parse", str(src), "-o", str(out), "--tier", tier]
        if "kit" not in Path(cli).name.lower():
            cmd += ["--pages", "all"]
        return cmd, out
    out = work / "mineru_out"
    out.mkdir(parents=True, exist_ok=True)
    return [cli, "-p", str(src), "-o", str(out), "-m", "auto"], out


def _run_mineru(
    data: bytes,
    cli: str,
    flavor: str,
    tier: str,
    timeout: int,
    filename: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mineru-http-") as tmp:
        work = Path(tmp)
        src = work / (Path(filename).name or "input.pdf")
        src.write_bytes(data)
        cmd, primary = _build_command(cli, flavor, src, work, tier)
        logger.info("run: %s", " ".join(cmd))
        proc = subprocess.run(  # noqa: S603 (命令由启动参数拼接, 非 shell)
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"CLI 退出码 {proc.returncode}: {(proc.stderr or proc.stdout or '')[-400:]}"
            )
        return _collect(work, primary)


def _collect(work: Path, primary: Path) -> dict[str, Any]:
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

    content_list: Any = []
    cl_files = sorted(work.rglob("*content_list*.json"))
    if cl_files:
        try:
            content_list = json.loads(cl_files[0].read_text(encoding="utf-8"))
        except (ValueError, OSError):
            content_list = []

    images: dict[str, str] = {}
    for path in sorted(work.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        if len(images) >= _MAX_IMAGES:
            break
        raw = path.read_bytes()
        if len(raw) > _MAX_IMAGE_BYTES:
            continue
        try:
            rel = str(path.relative_to(work)).replace("\\", "/")
        except ValueError:
            rel = path.name
        images[rel] = base64.b64encode(raw).decode("ascii")

    return {"markdown": markdown, "content_list": content_list, "images": images}


def main() -> None:
    parser = argparse.ArgumentParser(description="Lumos · 内网 MinerU 解析服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认仅本机)")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--cli", default="mineru-kit", help="MinerU 可执行文件")
    parser.add_argument("--flavor", choices=("v4", "v2"), default="v4")
    parser.add_argument("--tier", default="standard", help="MinerU 4.x 解析档位")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--token", default="", help="可选 Bearer Token")
    args = parser.parse_args()

    MinerUHandler.cli = args.cli
    MinerUHandler.flavor = args.flavor
    MinerUHandler.tier = args.tier
    MinerUHandler.timeout = args.timeout
    MinerUHandler.token = args.token

    server = ThreadingHTTPServer((args.host, args.port), MinerUHandler)
    logger.info("MinerU HTTP 服务已启动: http://%s:%s/v1/file_parse", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
