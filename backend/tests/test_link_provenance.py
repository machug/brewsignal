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
    ModelRequest(parts=[ToolReturnPart("web_search", {"query": "https://echoed.example/?d=secret",
                                                      "results": [{"url": "https://www.brewersfriend.com/r/123"}]}, tool_call_id="c1")]),
    ModelRequest(parts=[ToolReturnPart("preview_recipe", {"sections": {"notes": "https://laundered.example/?d=x"}}, tool_call_id="c3")]),
    ModelRequest(parts=[ToolReturnPart("fetch_url", {"url": "https://read.example/page",
                                                     "links": [{"url": "https://beer.example/p?id=7"}]}, tool_call_id="c2")]),
]


@pytest.mark.parametrize("url", [
    "https://byo.com/recipes/pliny-clone",        # user, bare link, scheme added
    "http://www.byo.com/recipes/pliny-clone/",    # scheme/www/trailing slash ignored
    "https://example.com/a",
    "https://brewersfriend.com/r/123",            # search result
    "https://read.example/page#part-2",           # a page already opened (next part); fragment ignored
])
def test_links_from_the_user_and_tool_results_are_known(url):
    assert is_known(url, HISTORY)


@pytest.mark.parametrize("url", [
    "https://attacker.example/?d=my+secret+notes",      # composed by the model
    "https://beer.example/p?id=7",                      # listed ON a page: link menus could leak data
    "https://brewersfriend.com/r/123?.,;:!",            # trailing punctuation as data
    "https://brewersfriend.com/r/123///",               # extra slashes as data
    "http://brewersfriend.com:8443/r/123",              # port as data
    "https://u:secret@brewersfriend.com/r/123",         # userinfo as data
    "https://brewersfriend.com\\@attacker.example/r/123",  # parser differential
    "https://model-made.example/x",                     # only in the model's own text
    "https://also-model.example/y",                     # only in the model's own tool call
    "https://byo.com/recipes",                          # a different path
    "https://echoed.example/?d=secret",                 # only in web_search's echoed query (codex P1)
    "https://laundered.example/?d=x",                   # only in another tool's echoed input
])
def test_composed_links_are_not_known(url):
    assert not is_known(url, HISTORY)


def test_link_key_is_robust():
    assert link_key("https://WWW.Example.com/Path/?q=1#x") == "example.com/Path?q=1"
    assert link_key("http://[broken/") is None and link_key("") is None
