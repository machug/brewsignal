"""Links the assistant may open without asking (tilt_ui-eevz.10)."""

import json

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from backend.services.link_provenance import is_known, link_key

HISTORY = [
    ModelRequest(parts=[UserPromptPart("Clone this: byo.com/recipes/pliny-clone and https://example.com/a/")]),
    ModelResponse(parts=[TextPart("I'll open https://model-made.example/x"),
                         ToolCallPart("web_search", {"query": "https://also-model.example/y"}, tool_call_id="c1")]),
    ModelRequest(parts=[ToolReturnPart("web_search", {"results": [{"url": "https://www.brewersfriend.com/r/123"}]}, tool_call_id="c1")]),
    ModelRequest(parts=[ToolReturnPart("fetch_url", {"links": [{"url": "https://beer.example/p?id=7"}]}, tool_call_id="c2")]),
]


@pytest.mark.parametrize("url", [
    "https://byo.com/recipes/pliny-clone",        # user, bare link, scheme added
    "http://www.byo.com/recipes/pliny-clone/",    # scheme/www/trailing slash ignored
    "https://example.com/a",
    "https://brewersfriend.com/r/123",            # search result
    "https://beer.example/p?id=7#reviews",        # link on a fetched page; fragment ignored
])
def test_links_from_the_user_and_tool_results_are_known(url):
    assert is_known(url, HISTORY)


@pytest.mark.parametrize("url", [
    "https://attacker.example/?d=my+secret+notes",      # composed by the model
    "https://beer.example/p?id=7&leak=notes",           # known page with data glued on
    "https://model-made.example/x",                     # only in the model's own text
    "https://also-model.example/y",                     # only in the model's own tool call
    "https://byo.com/recipes",                          # a different path
])
def test_composed_links_are_not_known(url):
    assert not is_known(url, HISTORY)


def test_link_key_is_robust():
    assert link_key("https://WWW.Example.com/Path/?q=1#x") == "example.com/Path?q=1"
    assert link_key("http://[broken/") is None and link_key("") is None
