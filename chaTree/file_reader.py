"""文件读取工具：支持纯文本、PDF、DOCX 等格式的内容提取。"""

from __future__ import annotations

import pathlib

# ── 支持的扩展名 ──

_CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".cs", ".sh", ".bat",
    ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".html",
    ".css", ".scss", ".less", ".sql", ".r", ".m", ".lua", ".pl", ".dart",
    ".vue", ".svelte",
}

_TEXT_EXTS = {".txt", ".md", ".rst", ".log", ".csv", ".tsv"}

_PDF_EXTS = {".pdf"}

_DOCX_EXTS = {".docx"}

ALL_EXTS = _CODE_EXTS | _TEXT_EXTS | _PDF_EXTS | _DOCX_EXTS

# ── 文件对话框过滤器 ──

_CODE_FILTER = " ".join(f"*{e}" for e in sorted(_CODE_EXTS))
_TEXT_FILTER = " ".join(f"*{e}" for e in sorted(_TEXT_EXTS))

FILE_DIALOG_FILTER = (
    f"所有支持格式 ({_CODE_FILTER} {_TEXT_FILTER} *.pdf *.docx);;"
    f"代码文件 ({_CODE_FILTER});;"
    f"PDF 文档 (*.pdf);;"
    f"Word 文档 (*.docx);;"
    f"文本文件 ({_TEXT_FILTER});;"
    f"所有文件 (*)"
)

# ── 扩展名 → 图标 ──

_ICON_MAP = {
    ".py": "🐍", ".js": "🟨", ".ts": "🟦", ".jsx": "⚛️", ".tsx": "⚛️",
    ".java": "☕", ".c": "⚙️", ".cpp": "⚙️", ".h": "⚙️", ".hpp": "⚙️",
    ".go": "🔵", ".rs": "🦀", ".rb": "💎", ".php": "🐘", ".swift": "🪽",
    ".kt": "🅺", ".cs": "🟣", ".sh": "🐚", ".bat": "🪟",
    ".json": "📋", ".xml": "📋", ".yaml": "📋", ".yml": "📋",
    ".toml": "📋", ".ini": "📋", ".cfg": "📋",
    ".html": "🌐", ".css": "🎨", ".scss": "🎨", ".less": "🎨",
    ".sql": "🗄️", ".r": "📊", ".m": "📊", ".lua": "🌙", ".pl": "🐪",
    ".dart": "🎯", ".vue": "💚", ".svelte": "🧡",
    ".txt": "📄", ".md": "📝", ".rst": "📝", ".log": "📜",
    ".csv": "📊", ".tsv": "📊",
    ".pdf": "📕", ".docx": "📘",
}

# ── 扩展名 → markdown 代码块语言标记 ──

_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".swift": "swift", ".kt": "kotlin", ".cs": "csharp",
    ".sh": "bash", ".bat": "batch",
    ".json": "json", ".xml": "xml", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".ini": "ini",
    ".html": "html", ".css": "css", ".scss": "scss", ".less": "less",
    ".sql": "sql", ".r": "r", ".m": "matlab", ".lua": "lua",
    ".pl": "perl", ".dart": "dart", ".vue": "html", ".svelte": "html",
    ".md": "markdown",
}


def get_icon(path: str) -> str:
    ext = pathlib.Path(path).suffix.lower()
    return _ICON_MAP.get(ext, "📎")


def get_language_hint(path: str) -> str:
    ext = pathlib.Path(path).suffix.lower()
    return _LANG_MAP.get(ext, "")


def read_file(path: str) -> tuple[str, str | None]:
    """读取文件内容。返回 (content, error)。

    成功时 content 为文件文本，error 为 None。
    失败时 content 为错误描述，error 为错误信息。
    """
    ext = pathlib.Path(path).suffix.lower()

    # PDF
    if ext == ".pdf":
        return _read_pdf(path)

    # DOCX
    if ext == ".docx":
        return _read_docx(path)

    # 纯文本 / 代码
    return _read_text(path)


def _read_text(path: str) -> tuple[str, str | None]:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(), None
    except UnicodeDecodeError:
        try:
            with open(path, encoding="latin-1") as f:
                return f.read(), None
        except Exception as e:
            return f"[读取失败] 无法解码文件：{e}", str(e)
    except Exception as e:
        return f"[读取失败] {e}", str(e)


def _read_pdf(path: str) -> tuple[str, str | None]:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return (
            "[PDF 读取失败] 请安装 PyPDF2：pip install PyPDF2",
            "PyPDF2 未安装",
        )
    try:
        reader = PdfReader(path)
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        content = "\n\n".join(pages)
        if not content.strip():
            return "[PDF 读取结果为空] 该 PDF 可能是扫描件或图片，无法提取文本。", None
        return content, None
    except Exception as e:
        return f"[PDF 读取失败] {e}", str(e)


def _read_docx(path: str) -> tuple[str, str | None]:
    try:
        from docx import Document
    except ImportError:
        return (
            "[DOCX 读取失败] 请安装 python-docx：pip install python-docx",
            "python-docx 未安装",
        )
    try:
        doc = Document(path)
        paragraphs: list[str] = []
        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text)
        content = "\n".join(paragraphs)
        if not content.strip():
            return "[DOCX 读取结果为空] 文档无文本内容。", None
        return content, None
    except Exception as e:
        return f"[DOCX 读取失败] {e}", str(e)
