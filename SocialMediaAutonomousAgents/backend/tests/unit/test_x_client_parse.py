from datetime import datetime, timezone

from app.social.dtos import PostData
from app.social.implementations.x_client import _id_str, _parse_dt


def test_parse_dt_passes_through_datetime():
    d = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert _parse_dt(d) is d


def test_id_str_from_int():
    assert _id_str(2054643922534875136) == "2054643922534875136"
    assert _id_str(None) is None


def test_post_data_coerces_int_author_id():
    post = PostData(id="1", author_id=2054643922534875136)
    assert post.author_id == "2054643922534875136"


def test_parse_dt_parses_iso_string():
    s = "2024-06-01T12:00:00.000Z"
    out = _parse_dt(s)
    assert out is not None
    assert out.year == 2024 and out.month == 6
