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
    ModelPreset("OpenAI · GPT-5.5", "gpt-5.5", _OPENAI),
    ModelPreset("OpenAI · GPT-5.4", "gpt-5.4", _OPENAI),
    ModelPreset("OpenAI · GPT-5", "gpt-5", _OPENAI),
    ModelPreset("OpenAI · GPT-4o mini", "gpt-4o-mini", _OPENAI),
    # Google Gemini（OpenAI 兼容层，需 Gemini API Key）
    ModelPreset("Gemini · 3 Pro", "gemini-3-pro", _GEMINI),
    ModelPreset("Gemini · 3 Flash", "gemini-3-flash", _GEMINI),
    # DeepSeek
    ModelPreset("DeepSeek · V4 Pro", "deepseek-v4-pro", "https://api.deepseek.com"),
    ModelPreset("DeepSeek · V4 Flash", "deepseek-v4-flash", "https://api.deepseek.com"),
    # 通义千问
    ModelPreset(
        "通义千问 · Qwen3.7 Plus",
        "qwen3.7-plus",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    ModelPreset(
        "通义千问 · Qwen3.7 Max",
        "qwen3.7-max",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    # Moonshot / Kimi
    ModelPreset("Kimi · K2.6", "kimi-k2.6", "https://api.moonshot.cn/v1"),
    ModelPreset("Kimi · K2.5", "kimi-k2.5", "https://api.moonshot.cn/v1"),
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
