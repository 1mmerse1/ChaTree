"""内置模型与对应 OpenAI-兼容 Base URL（用户只需选模型 + 填 Key）。"""

from __future__ import annotations

from dataclasses import dataclass

_OPENAI = "https://api.openai.com/v1"
_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"


@dataclass(frozen=True, slots=True)
class ModelPreset:
    """展示名 + 请求用的 model id + 该厂商的 base_url（无末尾斜杠）。"""

    display_name: str
    model_id: str
    base_url: str


MODEL_PRESETS: tuple[ModelPreset, ...] = (
    # OpenAI GPT-5 系列（Chat Completions，同一 v1 端点）
    ModelPreset("OpenAI · GPT-5.4", "gpt-5.4", _OPENAI),
    ModelPreset("OpenAI · GPT-5.4 mini", "gpt-5.4-mini", _OPENAI),
    ModelPreset("OpenAI · GPT-5 mini", "gpt-5-mini", _OPENAI),
    ModelPreset("OpenAI · GPT-5", "gpt-5", _OPENAI),
    ModelPreset("OpenAI · GPT-4o mini", "gpt-4o-mini", _OPENAI),
    ModelPreset("OpenAI · GPT-4o", "gpt-4o", _OPENAI),
    ModelPreset("OpenAI · GPT-4 Turbo", "gpt-4-turbo", _OPENAI),
    # Google Gemini（OpenAI 兼容层，需 Gemini API Key）
    ModelPreset("Gemini · 2.5 Flash", "gemini-2.5-flash", _GEMINI),
    ModelPreset("Gemini · 2.5 Pro", "gemini-2.5-pro", _GEMINI),
    ModelPreset("Gemini · 2.0 Flash", "gemini-2.0-flash", _GEMINI),
    ModelPreset("Gemini · 1.5 Flash", "gemini-1.5-flash", _GEMINI),
    ModelPreset("Gemini · 1.5 Pro", "gemini-1.5-pro", _GEMINI),
    # 其他
    ModelPreset("DeepSeek · Chat", "deepseek-chat", "https://api.deepseek.com"),
    ModelPreset(
        "DeepSeek · Reasoner", "deepseek-reasoner", "https://api.deepseek.com"
    ),
    ModelPreset(
        "通义千问 · Plus",
        "qwen-plus",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    ModelPreset(
        "通义千问 · Turbo",
        "qwen-turbo",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    ModelPreset(
        "通义千问 · Max",
        "qwen-max",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    ModelPreset("Moonshot · 8K", "moonshot-v1-8k", "https://api.moonshot.cn/v1"),
    ModelPreset("Moonshot · 32K", "moonshot-v1-32k", "https://api.moonshot.cn/v1"),
)


def preset_index_for_workspace(model: str, base_url: str) -> int:
    """根据已保存的 model / base_url 选中列表行；对不上则退回 0。"""
    bu = (base_url or "").rstrip("/")
    m = (model or "").strip()
    for i, p in enumerate(MODEL_PRESETS):
        if p.model_id == m and p.base_url.rstrip("/") == bu:
            return i
    for i, p in enumerate(MODEL_PRESETS):
        if p.model_id == m:
            return i
    return 0
