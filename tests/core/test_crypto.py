import pytest

from rgcc.core.crypto import (
    compute_shared_key,
    decrypt_payload,
    derive_key,
    encrypt_payload,
    generate_ec_keypair,
)


def test_derive_key_is_deterministic():
    assert derive_key("secret", b"salt") == derive_key("secret", b"salt")


def test_derive_key_changes_with_password_and_salt():
    assert derive_key("a", b"salt") != derive_key("b", b"salt")
    assert derive_key("a", b"salt") != derive_key("a", b"other")


def test_generate_ec_keypair_returns_pem_public_key():
    private, public = generate_ec_keypair()
    assert private is not None
    assert public.startswith("-----BEGIN PUBLIC KEY-----")
    assert public.endswith("-----END PUBLIC KEY-----\n")


def test_ecdh_is_symmetric_and_auth_token_bound():
    a_priv, a_pub = generate_ec_keypair()
    b_priv, b_pub = generate_ec_keypair()
    ka = compute_shared_key(a_priv, b_pub, "token")
    kb = compute_shared_key(b_priv, a_pub, "token")
    assert ka == kb
    assert ka != compute_shared_key(a_priv, b_pub, "other-token")


def test_encrypt_decrypt_roundtrip():
    key = derive_key("secret", b"salt").hex()
    data = b"hello\x00world"
    encrypted = encrypt_payload(data, key)
    assert len(encrypted) > len(data)
    assert decrypt_payload(encrypted, key) == data


def test_encrypt_empty_payload():
    key = derive_key("secret", b"salt").hex()
    encrypted = encrypt_payload(b"", key)
    assert decrypt_payload(encrypted, key) == b""


def test_wrong_key_fails():
    key1 = derive_key("one", b"salt").hex()
    key2 = derive_key("two", b"salt").hex()
    encrypted = encrypt_payload(b"data", key1)
    with pytest.raises(Exception):
        decrypt_payload(encrypted, key2)


def test_corrupted_payload_fails():
    key = derive_key("secret", b"salt").hex()
    encrypted = bytearray(encrypt_payload(b"data", key))
    encrypted[-1] ^= 0xFF
    with pytest.raises(Exception):
        decrypt_payload(bytes(encrypted), key)
