"""
MiMo Model Wrapper Tests
Based on AgentScope ChatModelBase
"""

import json
import pytest
from agentscope.credential._openai import OpenAICredential
from agentscope.model._base import ChatResponse, TextBlock
from agentscope.message._base import Msg
from src.models.mimo_wrapper import MiMoChatModel, MiMoParameters, create_mimo_model


def _make_user_msg(text: str) -> Msg:
    """Helper to create a user Msg with correct AgentScope v2 format"""
    return Msg(name="user", role="user", content=[TextBlock(text=text)])


class TestMiMoOffline:
    """Offline mode tests"""

    def test_offline_when_no_config(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoChatModel(credential=credential)
        assert model.offline is True

    def test_offline_when_no_url(self):
        credential = OpenAICredential(api_key="sk-test", base_url="")
        model = MiMoChatModel(credential=credential)
        assert model.offline is True

    def test_online_mode(self):
        credential = OpenAICredential(api_key="sk-test", base_url="https://api.test.com")
        model = MiMoChatModel(credential=credential)
        assert model.offline is False

    @pytest.mark.asyncio
    async def test_offline_returns_mock(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoChatModel(credential=credential)
        msg = _make_user_msg("test input")
        response = await model._call_api("mimo", [msg])
        assert isinstance(response, ChatResponse)
        assert len(response.content) > 0
        assert isinstance(response.content[0], TextBlock)
        assert len(response.content[0].text) > 0

    @pytest.mark.asyncio
    async def test_offline_json_mode(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoChatModel(credential=credential)
        msg = _make_user_msg("output JSON findings")
        response = await model._call_api("mimo", [msg])
        text = response.content[0].text
        parsed = MiMoChatModel.extract_json(text)
        assert parsed is not None
        assert "offline" in parsed


class TestJsonExtract:
    """JSON extraction tests"""

    def test_extract_pure_json(self):
        result = MiMoChatModel.extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_from_markdown(self):
        text = "result:\n```json\n{\"findings\": []}\n```\nend."
        result = MiMoChatModel.extract_json(text)
        assert result == {"findings": []}

    def test_extract_json_array(self):
        text = "result: [{\"id\": 1}, {\"id\": 2}] end."
        result = MiMoChatModel.extract_json(text)
        assert len(result) == 2

    def test_extract_json_failure(self):
        result = MiMoChatModel.extract_json("no json here")
        assert result is None


class TestMiMoConfig:
    """Configuration tests"""

    def test_custom_parameters(self):
        params = MiMoParameters(max_tokens=2048, temperature=0.5)
        assert params.max_tokens == 2048
        assert params.temperature == 0.5

    def test_factory_function(self):
        model = create_mimo_model(
            api_url="https://api.test.com",
            api_key="sk-test",
            model_name="mimo-custom",
            max_tokens=2048,
            temperature=0.5,
        )
        assert isinstance(model, MiMoChatModel)
        assert model.model == "mimo-custom"
        assert model.parameters.max_tokens == 2048
        assert model.offline is False

    def test_factory_offline(self):
        model = create_mimo_model(api_url="", api_key="")
        assert model.offline is True

    def test_get_text(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoChatModel(credential=credential)
        response = ChatResponse(
            content=[TextBlock(text="Hello"), TextBlock(text=" World")],
            is_last=True,
        )
        assert model.get_text(response) == "Hello World"

    def test_get_json(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoChatModel(credential=credential)
        response = ChatResponse(
            content=[TextBlock(text='{"key": "value"}')],
            is_last=True,
        )
        result = model.get_json(response)
        assert result == {"key": "value"}
