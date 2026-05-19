from cryptography.fernet import Fernet

from app.utils.encryption import decrypt_value, encrypt_value, fernet_from_key


def test_encrypt_roundtrip():
    key = Fernet.generate_key().decode()
    f = fernet_from_key(key)
    plain = "consumer-secret-xyz"
    token = encrypt_value(f, plain)
    assert token != plain
    assert decrypt_value(f, token) == plain


def test_wrong_key_fails():
    f1 = fernet_from_key(Fernet.generate_key().decode())
    f2 = fernet_from_key(Fernet.generate_key().decode())
    token = encrypt_value(f1, "hello")
    try:
        decrypt_value(f2, token)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
