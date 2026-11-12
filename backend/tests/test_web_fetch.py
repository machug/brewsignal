"""Assistant page reading: public-only, readable text, structured data, paging (tilt_ui-eevz.4)."""

import socket

import httpx
import pytest

from backend.services import web_fetch as wf

PUBLIC_IP = "93.184.216.34"


def _resolve(monkeypatch, table):
    """Fake DNS: hostname -> IP."""
    async def getaddrinfo(host, port, type=0):
        ip = table.get(host, host)
        fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(fam, socket.SOCK_STREAM, 6, "", (ip, port))]

    class Loop:
        pass

    loop = Loop()
    loop.getaddrinfo = getaddrinfo
    monkeypatch.setattr(wf.asyncio, "get_running_loop", lambda: loop)


def _serve(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(wf.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
@pytest.mark.parametrize("url,ip", [
    ("http://localhost:8080/api/config", "127.0.0.1"),
    ("http://brewsignal.local/", "192.168.4.218"),
    ("http://metadata.example/latest", "169.254.169.254"),
    ("http://v6.example/", "::1"),
    ("http://10.0.0.5/", "10.0.0.5"),
])
async def test_private_addresses_are_refused(monkeypatch, url, ip):
    _resolve(monkeypatch, {urlhost: ip for urlhost in [httpx.URL(url).host]})
    _serve(monkeypatch, lambda r: httpx.Response(200, text="secret"))
    out = await wf.fetch_page(url)
    assert "Not fetched" in out["error"], out


@pytest.mark.asyncio
async def test_redirect_into_the_home_network_is_refused(monkeypatch):
    _resolve(monkeypatch, {"public.example": PUBLIC_IP, "ha.local": "192.168.4.10"})

    def handler(request):
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://ha.local:8123/api/states"})
        return httpx.Response(200, text="home assistant states")

    _serve(monkeypatch, handler)
    out = await wf.fetch_page("https://public.example/beer")
    assert "Not fetched" in out["error"], out


@pytest.mark.asyncio
async def test_non_http_schemes_are_refused():
    assert "Not fetched" in (await wf.fetch_page("file:///etc/passwd"))["error"]


PAGE = """<!doctype html><html><head><title> Pliny the Elder | Russian River </title>
<meta name="description" content="Double IPA, 8% ABV, 100 IBU">
<script type="application/ld+json">{"@type": "Recipe", "name": "Pliny clone", "recipeIngredient": ["Magnum 100 g"]}</script>
<script>var tracking = "ignore me";</script><style>.x{color:red}</style></head>
<body><nav>Home | Beers | Shop</nav><header>Site banner</header>
<main><h1>Pliny the Elder</h1><p>A hop-forward double IPA.</p>
<ul><li>Simcoe</li><li>Columbus</li></ul>
<table><tr><th>Hop</th><th>Grams</th></tr><tr><td>Simcoe</td><td>50</td></tr></table></main>
<footer>Copyright</footer></body></html>"""


@pytest.mark.asyncio
async def test_page_is_turned_into_readable_text_with_structured_data(monkeypatch):
    _resolve(monkeypatch, {"rr.example": PUBLIC_IP})
    _serve(monkeypatch, lambda r: httpx.Response(200, text=PAGE, headers={"content-type": "text/html; charset=utf-8"}))
    out = await wf.fetch_page("https://rr.example/pliny")
    assert out["title"] == "Pliny the Elder | Russian River"
    assert out["description"] == "Double IPA, 8% ABV, 100 IBU"
    assert out["structured_data"][0]["name"] == "Pliny clone"
    text = out["content"]
    assert "# Pliny the Elder" in text and "- Simcoe" in text and "| Simcoe | 50" in text
    for junk in ("tracking", "color:red", "Home | Beers", "Site banner", "Copyright"):
        assert junk not in text, junk
    assert "Untrusted" in out["note"]


@pytest.mark.asyncio
async def test_long_pages_come_in_parts(monkeypatch):
    _resolve(monkeypatch, {"long.example": PUBLIC_IP})
    body = "<html><body>" + "".join(f"<p>line {i} " + "x" * 90 + "</p>" for i in range(400)) + "</body></html>"
    _serve(monkeypatch, lambda r: httpx.Response(200, text=body, headers={"content-type": "text/html"}))
    first = await wf.fetch_page("https://long.example/")
    assert len(first["content"]) == wf.PAGE_CHARS and first["next_offset"] == wf.PAGE_CHARS
    second = await wf.fetch_page("https://long.example/", offset=first["next_offset"])
    assert "title" not in second and second["content"]


@pytest.mark.asyncio
async def test_pdf_is_declined_politely(monkeypatch):
    _resolve(monkeypatch, {"pdf.example": PUBLIC_IP})
    _serve(monkeypatch, lambda r: httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}))
    assert "Cannot read" in (await wf.fetch_page("https://pdf.example/x.pdf"))["error"]
