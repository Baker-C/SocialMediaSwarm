from pathlib import Path

from app.infrastructure.ravendb_http import discover_ravendb_client_cert_paths


def test_discover_prefers_pem_and_key(tmp_path: Path) -> None:
    d = tmp_path / "ravendb" / "certs"
    d.mkdir(parents=True)
    (d / "client.pem").write_text("cert", encoding="utf-8")
    (d / "client.key").write_text("key", encoding="utf-8")
    c, k = discover_ravendb_client_cert_paths(d)
    assert c == str(d / "client.pem")
    assert k == str(d / "client.key")


def test_discover_pem_only(tmp_path: Path) -> None:
    d = tmp_path / "certs"
    d.mkdir()
    (d / "client.pem").write_text("both", encoding="utf-8")
    c, k = discover_ravendb_client_cert_paths(d)
    assert c == str(d / "client.pem")
    assert k is None


def test_discover_crt_key(tmp_path: Path) -> None:
    d = tmp_path / "certs"
    d.mkdir()
    (d / "client.crt").write_text("crt", encoding="utf-8")
    (d / "client.key").write_text("key", encoding="utf-8")
    c, k = discover_ravendb_client_cert_paths(d)
    assert c == str(d / "client.crt")
    assert k == str(d / "client.key")


def test_discover_missing_dir(tmp_path: Path) -> None:
    c, k = discover_ravendb_client_cert_paths(tmp_path / "nope")
    assert c is None and k is None


def test_discover_instance_crt_key(tmp_path: Path) -> None:
    d = tmp_path / "certs"
    d.mkdir()
    (d / "ravendb-tortellini-soup.instance.crt").write_text("crt", encoding="utf-8")
    (d / "ravendb-tortellini-soup.instance.key").write_text("key", encoding="utf-8")
    c, k = discover_ravendb_client_cert_paths(d)
    assert c == str(d / "ravendb-tortellini-soup.instance.crt")
    assert k == str(d / "ravendb-tortellini-soup.instance.key")
