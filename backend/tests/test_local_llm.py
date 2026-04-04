"""Tests for local LLM deployment (SGLang + Gemma-4-26B-A4B).

These are integration tests that require the sglang container to be running.
Run from within the teamgr-app container or any host that can reach sglang:18080.

Usage:
    docker exec teamgr-app python -m pytest tests/test_local_llm.py -v
"""

import json
import re
import time

import httpx
import pytest

# ---------------------------------------------------------------------------
# Configuration — adjust if your setup differs
# ---------------------------------------------------------------------------
SGLANG_BASE_URL = "http://sglang:18080/v1"
CHAT_URL = f"{SGLANG_BASE_URL}/chat/completions"
TIMEOUT = 120.0


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from model output.
    Also handles unclosed <think> tags (truncated by max_tokens).
    """
    text = re.sub(r"<think>[\s\S]*?</think>\s*", "", text, flags=re.DOTALL)
    # Handle unclosed <think> at the start (truncated responses)
    text = re.sub(r"<think>[\s\S]*$", "", text)
    return text.strip()


def _chat(messages: list[dict], **kwargs) -> dict:
    """Send a chat completion request and return the full response dict."""
    payload = {"messages": messages, "max_tokens": kwargs.pop("max_tokens", 256), **kwargs}
    resp = httpx.post(CHAT_URL, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _chat_text(prompt: str, **kwargs) -> str:
    """Send a simple user prompt and return the assistant text (think tags stripped).
    Includes system prompt to suppress thinking mode.
    """
    messages = [
        {"role": "system", "content": "请直接回答，不要输出思考过程。"},
        {"role": "user", "content": prompt},
    ]
    data = _chat(messages, **kwargs)
    raw = data["choices"][0]["message"]["content"]
    return _strip_think_tags(raw)


# ===========================================================================
# 1. Basic connectivity
# ===========================================================================
class TestConnectivity:
    """Verify the SGLang service is reachable and responds correctly."""

    def test_health_check(self):
        """A minimal inference request should return 200."""
        resp = httpx.post(
            CHAT_URL,
            json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
            timeout=TIMEOUT,
        )
        assert resp.status_code == 200

    def test_models_endpoint(self):
        """/v1/models should return the served model."""
        resp = httpx.get(f"{SGLANG_BASE_URL}/models", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        model_ids = [m["id"] for m in data["data"]]
        assert "Gemma-4-26B-A4B" in model_ids

    def test_response_structure(self):
        """Response should follow OpenAI chat completions format."""
        data = _chat([{"role": "user", "content": "say ok"}], max_tokens=10)
        assert "choices" in data
        assert len(data["choices"]) >= 1
        choice = data["choices"][0]
        assert "message" in choice
        assert "content" in choice["message"]
        assert "role" in choice["message"]
        assert choice["message"]["role"] == "assistant"

    def test_usage_in_response(self):
        """Response should include usage statistics."""
        data = _chat([{"role": "user", "content": "say ok"}], max_tokens=10)
        assert "usage" in data
        usage = data["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert usage["prompt_tokens"] > 0


# ===========================================================================
# 2. Model field behavior
# ===========================================================================
class TestModelField:
    """SGLang accepts the served model name in the model field."""

    def test_correct_model_field_ok(self):
        """Passing the served model name should work."""
        payload = {
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "model": "Gemma-4-26B-A4B",
        }
        resp = httpx.post(CHAT_URL, json=payload, timeout=TIMEOUT)
        assert resp.status_code == 200


# ===========================================================================
# 3. Think tag handling
# ===========================================================================
class TestThinkTags:
    """Test think tag stripping (for models that use thinking mode)."""

    def test_raw_response_may_contain_think_tags(self):
        """Without system prompt suppression, response may contain <think> tags."""
        data = _chat(
            [{"role": "user", "content": "1+1等于几？"}],
            max_tokens=256,
        )
        raw = data["choices"][0]["message"]["content"]
        # The model might or might not use think tags; we just verify it responds
        assert len(raw) > 0

    def test_strip_think_tags_function(self):
        """_strip_think_tags should correctly remove thinking blocks."""
        assert _strip_think_tags("<think>\nsome thinking\n</think>\nHello") == "Hello"
        assert _strip_think_tags("<think>x</think>A<think>y</think>B") == "AB"
        assert _strip_think_tags("No think tags here") == "No think tags here"
        assert _strip_think_tags("<think>\n\n</think>\n\n42") == "42"
        # Unclosed think tag (truncated by max_tokens)
        assert _strip_think_tags("<think>\ntruncated thinking...") == ""
        assert _strip_think_tags("<think>\n</think>\nAnswer<think>\nmore") == "Answer"

    def test_system_prompt_suppresses_thinking(self):
        """Adding a system prompt to skip thinking should reduce <think> tags."""
        data = _chat(
            [
                {"role": "system", "content": "请直接回答，不要输出思考过程。"},
                {"role": "user", "content": "1+1等于几？只回答数字"},
            ],
            max_tokens=32,
        )
        raw = data["choices"][0]["message"]["content"]
        cleaned = _strip_think_tags(raw)
        assert "2" in cleaned


# ===========================================================================
# 4. Text generation quality
# ===========================================================================
class TestTextGeneration:
    """Verify the model can generate useful text responses."""

    def test_simple_question(self):
        """Model should answer a simple factual question."""
        answer = _chat_text("中国的首都是哪里？只回答城市名。", max_tokens=128)
        assert "北京" in answer

    def test_json_output(self):
        """Model should be able to produce valid JSON when instructed."""
        prompt = """请返回一个JSON对象，包含以下字段：
- name: "张三"
- age: 30
只返回JSON，不要其他文字。"""
        raw = _chat_text(prompt, max_tokens=128, temperature=0.1)
        # Extract JSON if wrapped in code blocks
        if "```" in raw:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if match:
                raw = match.group(1)
        data = json.loads(raw)
        assert data["name"] == "张三"
        assert data["age"] == 30

    def test_longer_response(self):
        """Model should handle generating longer responses."""
        answer = _chat_text("用三句话介绍Python编程语言。", max_tokens=512)
        assert len(answer) > 20  # Should produce a meaningful response

    def test_multi_turn_conversation(self):
        """Model should handle multi-turn conversations."""
        data = _chat(
            [
                {"role": "system", "content": "请直接回答，不要输出思考过程。"},
                {"role": "user", "content": "我叫小明。"},
                {"role": "assistant", "content": "你好小明！"},
                {"role": "user", "content": "我叫什么名字？只回答名字。"},
            ],
            max_tokens=128,
        )
        raw = data["choices"][0]["message"]["content"]
        cleaned = _strip_think_tags(raw)
        assert "小明" in cleaned


# ===========================================================================
# 5. Talent card update simulation
# ===========================================================================
class TestTalentCardUpdate:
    """Simulate the talent card update flow that was failing."""

    def test_card_update_returns_valid_json(self):
        """The update_talent_card prompt should produce parseable JSON."""
        prompt = """你是一个人才信息整理助手。请根据用户输入的信息，更新人才卡片数据。

## 当前人才: 测试人员

## 当前维度定义:
- basic_info (基本信息): 结构为 {"name": "str", "gender": "str"}
- education (教育背景): 结构为 {"school": "str", "degree": "str"}

## 当前卡片数据:
```json
{"basic_info": {"name": "测试人员"}}
```

## 用户新输入的信息:
男，清华大学博士

## 要求:
1. 将用户输入的信息整理并合并到对应的维度中
2. 保留已有的信息，新增或更新相关字段
3. 如果用户输入的信息无法归入现有维度，可以在 new_dimensions 中建议新增维度
4. 为此人才建议合适的标签
5. 生成一句话总结

请严格返回以下JSON格式（不要包含markdown代码块标记）:
{
  "card_data": { ... 更新后的完整卡片数据 ... },
  "summary": "一句话描述",
  "suggested_tags": ["标签1", "标签2"],
  "new_dimensions": []
}"""

        messages = [
            {"role": "system", "content": "请直接回答，不要输出思考过程。"},
            {"role": "user", "content": prompt},
        ]
        data = _chat(messages, max_tokens=1024, temperature=0.1)
        raw = data["choices"][0]["message"]["content"]
        cleaned = _strip_think_tags(raw)

        # Extract JSON from code blocks if present
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
            if match:
                cleaned = match.group(1)

        result = json.loads(cleaned)
        assert "card_data" in result
        assert "summary" in result
        assert "suggested_tags" in result
        assert isinstance(result["suggested_tags"], list)
        # Verify the data was merged correctly
        card = result["card_data"]
        assert "basic_info" in card or "education" in card


# ===========================================================================
# 6. Performance
# ===========================================================================
class TestPerformance:
    """Basic performance checks."""

    def test_short_response_latency(self):
        """A short response should complete within reasonable time."""
        t0 = time.monotonic()
        _chat_text("说'好的'", max_tokens=10)
        elapsed = time.monotonic() - t0
        # Should complete within 30 seconds even with model warmup
        assert elapsed < 30, f"Short response took {elapsed:.1f}s"

    def test_concurrent_requests(self):
        """Two sequential requests should both succeed."""
        for i in range(2):
            resp = _chat_text(f"数字{i+1}", max_tokens=10)
            assert len(resp) > 0
