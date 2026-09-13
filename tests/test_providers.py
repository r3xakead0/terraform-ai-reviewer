from __future__ import annotations

import json
from pathlib import Path

from terraform_ai_reviewer.models import Limits
from terraform_ai_reviewer.plan import build_context, load_plan
from terraform_ai_reviewer.providers import review_with_bedrock

FIXTURES = Path(__file__).parents[1] / "fixtures"


class FakeBedrock:
    def __init__(self, response: dict | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.request: dict | None = None

    def converse(self, **kwargs: object) -> dict:
        self.request = kwargs
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def _context():
    return build_context(load_plan(FIXTURES / "tfplan.json"), [], Limits())


def test_bedrock_uses_structured_converse_output() -> None:
    analysis = json.loads((FIXTURES / "bedrock-response.json").read_text())
    client = FakeBedrock(
        {"output": {"message": {"content": [{"text": json.dumps(analysis)}]}}}
    )
    result = review_with_bedrock(_context(), "test-model", "us-east-1", client=client)

    assert result.status == "ok"
    assert result.analysis is not None
    assert result.analysis.risk_level == "critical"
    assert client.request is not None
    assert client.request["modelId"] == "test-model"
    assert client.request["inferenceConfig"] == {"maxTokens": 3000, "temperature": 0.0}
    assert client.request["outputConfig"]["textFormat"]["type"] == "json_schema"


def test_bedrock_failure_is_advisory_and_does_not_raise() -> None:
    result = review_with_bedrock(
        _context(),
        "test-model",
        "us-east-1",
        client=FakeBedrock(error=TimeoutError("request content must not be echoed")),
    )
    assert result.status == "unavailable"
    assert result.message == "AI analysis unavailable (TimeoutError)."
    assert "request content" not in result.message


def test_invalid_bedrock_schema_is_advisory() -> None:
    client = FakeBedrock(
        {"output": {"message": {"content": [{"text": '{"risk_level":"high"}'}]}}}
    )
    result = review_with_bedrock(_context(), "test-model", "us-east-1", client=client)
    assert result.status == "unavailable"
    assert result.message == "AI analysis unavailable (ValidationError)."
