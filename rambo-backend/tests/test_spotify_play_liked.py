"""play_liked: random-start by default, ordered when asked, graceful on errors."""

import random

import pytest

from spotify_client import SpotifyClient


def _client(liked_result):
    c = SpotifyClient(repo=None)
    captured = {}

    async def fake_liked(max_total=100):
        return liked_result

    async def fake_play(device_id=None, uris=None, **kw):
        captured["uris"] = uris
        return {"ok": True, "played": True}

    c.liked = fake_liked
    c.play = fake_play
    return c, captured


def _liked(n):
    return {"items": [{"track": {"uri": f"spotify:track:{i}"}} for i in range(n)]}


@pytest.mark.asyncio
async def test_ordered_when_randomize_false():
    c, cap = _client(_liked(5))
    await c.play_liked(randomize=False)
    assert cap["uris"] == [f"spotify:track:{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_random_is_a_permutation_and_reorders():
    c, cap = _client(_liked(20))
    original = [f"spotify:track:{i}" for i in range(20)]
    random.seed(1)
    await c.play_liked(randomize=True)
    assert sorted(cap["uris"]) == sorted(original)   # same set, none lost
    assert cap["uris"] != original                   # actually reordered


@pytest.mark.asyncio
async def test_no_liked_songs():
    c, cap = _client({"items": []})
    res = await c.play_liked()
    assert res == {"error": "no_liked_songs"}
    assert "uris" not in cap                          # play never called


@pytest.mark.asyncio
async def test_surfaces_api_error():
    c, cap = _client({"error": "not_connected"})
    res = await c.play_liked()
    assert res == {"error": "not_connected"}
    assert "uris" not in cap


@pytest.mark.asyncio
async def test_skips_null_or_uriless_tracks():
    c, cap = _client({"items": [
        {"track": {"uri": "spotify:track:a"}},
        {"track": None},
        {"track": {}},                  # no uri
        {"track": {"uri": "spotify:track:b"}},
    ]})
    await c.play_liked(randomize=False)
    assert cap["uris"] == ["spotify:track:a", "spotify:track:b"]
