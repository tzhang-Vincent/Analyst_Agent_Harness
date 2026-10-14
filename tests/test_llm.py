from types import SimpleNamespace

from agent.llm import (
    build_intent_tool,
    parse_anthropic_response,
    parse_openai_response,
    to_anthropic_tools,
)


def test_to_anthropic_tools():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "parse_intent",
                "description": "d",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    out = to_anthropic_tools(tools)
    assert out == [
        {
            "name": "parse_intent",
            "description": "d",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


def test_parse_openai_response():
    resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="hi",
                    tool_calls=[
                        SimpleNamespace(
                            id="t1",
                            function=SimpleNamespace(
                                name="parse_intent", arguments='{"tickers": ["NVDA"]}'
                            ),
                        )
                    ],
                )
            )
        ]
    )
    out = parse_openai_response(resp)
    assert out["content"] == "hi"
    assert out["tool_calls"] == [
        {"id": "t1", "name": "parse_intent", "arguments": {"tickers": ["NVDA"]}}
    ]


def test_parse_anthropic_response():
    resp = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="hello "),
            SimpleNamespace(type="tool_use", id="t2", name="g", input={"b": 2}),
        ]
    )
    out = parse_anthropic_response(resp)
    assert out["content"] == "hello "
    assert out["tool_calls"] == [{"id": "t2", "name": "g", "arguments": {"b": 2}}]


def test_build_intent_tool_schema():
    tool = build_intent_tool()
    assert tool["function"]["name"] == "parse_intent"
    props = tool["function"]["parameters"]["properties"]
    assert set(props) == {"tickers", "metrics", "num_periods", "frequency"}
