"""Assistant page reading: public-only, pinned connections, readable text, paging (tilt_ui-eevz.4)."""

import socket

import httpx
import pytest

from backend.services import web_fetch as wf

PUBLIC_IP = "93.184.216.34"


def _resolve(monkeypatch, table):
    """Fake DNS: hostname -> IP (real getaddrinfo tuple shapes)."""
    async def getaddrinfo(host, port, type=0):
        ip = table.get(host, host)
        if ":" in ip:
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, port, 0, 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    class Loop:
        pass

    loop = Loop()
    loop.getaddrinfo = getaddrinfo
    monkeypatch.setattr(wf.asyncio, "get_running_loop", lambda: loop)


def _serve(monkeypatch, handler, seen=None):
    real = httpx.AsyncClient

    def wrapped(request):
        if seen is not None:
            seen.append(request)
        return handler(request)

    monkeypatch.setattr(wf.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(wrapped), **kw))


def _resp(status, body=b"", headers=None):
    """A streamed response like a real network one (aiter_raw works on it)."""
    data = body.encode() if isinstance(body, str) else body
    return httpx.Response(status, headers=headers or {}, stream=httpx.ByteStream(data))


def _site(request) -> str:
    return request.headers["host"]


# --- where it may connect ----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("url,ip", [
    ("http://localhost/api/config", "127.0.0.1"),
    ("http://brewsignal.local/", "192.168.4.218"),
    ("http://metadata.example/latest", "169.254.169.254"),
    ("http://v6loop.example/", "::1"),
    ("http://mapped.example/", "::ffff:127.0.0.1"),
    ("http://nat64.example/", "64:ff9b::a9fe:a9fe"),
    ("http://cgnat.example/", "100.64.1.1"),
    ("http://10.0.0.5/", "10.0.0.5"),
])
async def test_private_addresses_are_refused(monkeypatch, url, ip):
    _resolve(monkeypatch, {httpx.URL(url).host: ip})
    _serve(monkeypatch, lambda r: _resp(200, "secret"))
    out = await wf.fetch_page(url)
    assert "Not fetched" in out["error"], out


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "https://user:pass@public.example/",
    "http://public.example:22/",
    "http://public.example:6379/",
    "https://example.com:bad/",
    "http://[broken/",
    "",
    "not a url",
])
async def test_disallowed_or_malformed_urls_return_errors(monkeypatch, url):
    _resolve(monkeypatch, {"public.example": PUBLIC_IP})
    _serve(monkeypatch, lambda r: _resp(200, "x"))
    out = await wf.fetch_page(url)
    assert "error" in out, out


@pytest.mark.asyncio
async def test_connects_to_the_checked_address_with_the_real_host_name(monkeypatch):
    """DNS rebinding: the request goes to the IP that passed the check, not a fresh lookup."""
    _resolve(monkeypatch, {"public.example": PUBLIC_IP})
    seen = []
    _serve(monkeypatch, lambda r: _resp(200, "<html><body><p>ok</p></body></html>", {"content-type": "text/html"}), seen)
    out = await wf.fetch_page("https://public.example/beer?x=1")
    assert out["content"] == "ok"
    req = seen[0]
    assert req.url.host == PUBLIC_IP and req.url.path == "/beer" and req.url.query == b"x=1"
    assert req.headers["host"] == "public.example"
    assert req.extensions.get("sni_hostname") == "public.example"
    assert req.headers["accept-encoding"] == "identity"


@pytest.mark.asyncio
async def test_redirect_into_the_home_network_is_refused(monkeypatch):
    _resolve(monkeypatch, {"public.example": PUBLIC_IP, "ha.local": "192.168.4.10"})

    def handler(request):
        if _site(request) == "public.example":
            return _resp(302, headers={"location": "http://ha.local/api/states"})
        return _resp(200, "home assistant states")

    _serve(monkeypatch, handler)
    out = await wf.fetch_page("https://public.example/beer")
    assert "Not fetched" in out["error"], out


@pytest.mark.asyncio
async def test_binary_content_is_refused_before_reading(monkeypatch):
    _resolve(monkeypatch, {"pdf.example": PUBLIC_IP})
    _serve(monkeypatch, lambda r: _resp(200, b"%PDF-1.7", {"content-type": "application/pdf"}))
    assert "Cannot read" in (await wf.fetch_page("https://pdf.example/x.pdf"))["error"]


@pytest.mark.asyncio
async def test_compressed_body_is_not_inflated(monkeypatch):
    _resolve(monkeypatch, {"gz.example": PUBLIC_IP})
    _serve(monkeypatch, lambda r: _resp(200, b"\x1f\x8b...", {"content-type": "text/html", "content-encoding": "gzip"}))
    assert "compressed" in (await wf.fetch_page("https://gz.example/"))["error"]


def test_client_ignores_environment_proxies(monkeypatch):
    captured = {}
    real = httpx.AsyncClient

    def spy(**kw):
        captured.update(kw)
        return real(**kw)

    monkeypatch.setattr(wf.httpx, "AsyncClient", spy)
    import asyncio
    asyncio.run(wf.fetch_page("http://127.0.0.1/"))  # blocked before any request, but the client was built
    assert captured["trust_env"] is False


# --- reading -----------------------------------------------------------------

PAGE = """<!doctype html><html><head><title> Pliny the Elder | Russian River </title>
<meta name="description" content="Double IPA, 8% ABV, 100 IBU">
<script type="application/ld+json; charset=utf-8">{"@type": "Recipe", "name": "Pliny clone", "recipeIngredient": ["Magnum 100 g"]}</script>
<script>var tracking = "ignore me";</script><style>.x{color:red}</style></head>
<body><nav>Home | Beers | Shop<svg><title>Search icon</title></svg></nav>
<main><article><header><h1>Pliny the Elder</h1><p>8% ABV, 1.072 OG</p></header>
<p>A hop-forward double IPA at 65°C mash.</p>
<ul><li><p>Simcoe</p></li><li>Columbus</li></ul>
<form><ul class="ingredients"><li>Pale malt 6 kg</li></ul></form>
<table><tr><th>Hop</th><th>Grams</th></tr><tr><td><div>Simcoe</div></td><td><div>50</div></td></tr></table>
</article></main>
<aside>Related posts</aside>
<footer>Copyright</footer></body></html>"""


@pytest.mark.asyncio
async def test_page_is_turned_into_readable_text_with_structured_data(monkeypatch):
    _resolve(monkeypatch, {"rr.example": PUBLIC_IP})
    _serve(monkeypatch, lambda r: _resp(200, PAGE, {"content-type": "text/html; charset=utf-8"}))
    out = await wf.fetch_page("https://rr.example/pliny")
    assert out["title"] == "Pliny the Elder | Russian River"  # not "...Search icon"
    assert out["description"] == "Double IPA, 8% ABV, 100 IBU"
    assert out["structured_data"][0]["name"] == "Pliny clone"
    text = out["content"]
    for kept in ("# Pliny the Elder", "8% ABV, 1.072 OG", "65°C", "- Simcoe", "- Pale malt 6 kg", "| Simcoe | 50"):
        assert kept in text, (kept, text)
    for junk in ("tracking", "color:red", "Home | Beers", "Related posts", "Copyright"):
        assert junk not in text, junk
    assert "Untrusted" in out["note"]


def test_unclosed_and_stray_tags_do_not_blank_or_leak():
    out = wf.extract_html("<body><p>before</p><aside>ad<nav>menu</aside></nav><p>after</p></body>")
    assert "before" in out["text"] and "after" in out["text"]
    assert "ad" not in out["text"].split() and "menu" not in out["text"]


@pytest.mark.asyncio
async def test_unknown_charset_and_meta_charset(monkeypatch):
    _resolve(monkeypatch, {"cs.example": PUBLIC_IP})
    latin = "<html><head><meta charset='iso-8859-1'></head><body><p>Mash 65°C</p></body></html>".encode("latin-1")
    _serve(monkeypatch, lambda r: _resp(200, latin, {"content-type": "text/html; charset=bogus"}))
    out = await wf.fetch_page("https://cs.example/")
    assert "Mash 65°C" in out["content"]


@pytest.mark.asyncio
async def test_long_pages_come_in_parts(monkeypatch):
    _resolve(monkeypatch, {"long.example": PUBLIC_IP})
    body = "<html><body>" + "".join(f"<p>line {i} " + "x" * 90 + "</p>" for i in range(400)) + "</body></html>"
    _serve(monkeypatch, lambda r: _resp(200, body, {"content-type": "text/html"}))
    first = await wf.fetch_page("https://long.example/")
    assert len(first["content"]) == wf.PAGE_CHARS and first["next_offset"] == wf.PAGE_CHARS
    second = await wf.fetch_page("https://long.example/", offset=first["next_offset"])
    assert "title" not in second and second["content"]


def test_hostile_json_ld_is_capped():
    deep = "[" * 100_000 + "]" * 100_000
    out = wf.extract_html(f'<script type="application/ld+json">{deep}</script><p>x</p>')
    assert out["structured_data"] == [] and out["text"] == "x"
