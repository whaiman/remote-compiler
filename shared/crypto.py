import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric import ec


def derive_key(password: str, salt: bytes) -> bytes:
    """Generate a 256-bit key from a password and salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(password.encode())


def generate_ec_keypair():
    """Generate an EC private key and its corresponding PEM public key string."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, pub_bytes.decode("utf-8")


def compute_shared_key(private_key, peer_public_pem: str, auth_token: str) -> str:
    """Compute an AES-256 derived key securely using an ECDH exchange."""
    peer_pub_bytes = peer_public_pem.encode("utf-8")
    peer_public_key = serialization.load_pem_public_key(peer_pub_bytes)
    shared_key = private_key.exchange(ec.ECDH(), peer_public_key)

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"handshake_" + auth_token.encode("utf-8"),
    )
    aes_key = hkdf.derive(shared_key)
    return aes_key.hex()


def encrypt_payload(data: bytes, key_hex: str) -> bytes:
    """Encrypt data using AES-256-GCM.

    Returns: nonce (12 bytes) + tag (16 bytes) + ciphertext.
    Note: cryptography's AESGCM.encrypt returns ciphertext + tag.
    We return nonce + (ciphertext with tag).
    """
    key = bytes.fromhex(key_hex)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt_payload(payload: bytes, key_hex: str) -> bytes:
    """Decrypt payload using AES-256-GCM."""
    key = bytes.fromhex(key_hex)
    aesgcm = AESGCM(key)
    nonce = payload[:12]
    ciphertext = payload[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)
