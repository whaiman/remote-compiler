import logging
from pathlib import Path
from typing import Optional, cast

import httpx

from rgcc.core.crypto import (
    compute_shared_key,
    decrypt_payload,
    encrypt_payload,
    generate_ec_keypair,
)

logger = logging.getLogger("client.transport.api")


class ApiClient:
    def __init__(self, endpoint: str, auth_token: str) -> None:
        # Allow user to specify just base url or /api/compile
        if endpoint.endswith("/api/compile"):
            endpoint = endpoint[: -len("/api/compile")]
        self.endpoint: str = endpoint.rstrip("/")
        self.auth_token: str = auth_token
        self.session_id: Optional[str] = None
        self.encryption_key: Optional[str] = None

    async def negotiate_key(self) -> None:
        """Negotiate an AES encryption key via ECDH exchange."""
        priv, pub = generate_ec_keypair()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.endpoint}/api/handshake",
                json={"public_key": pub},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Handshake failed: {resp.text}")

            data = resp.json()
            server_pub = data["public_key"]
            self.session_id = data["session_id"]
            self.encryption_key = compute_shared_key(priv, server_pub, self.auth_token)

    async def send_payload(self, archive_path: Path) -> bytes:
        """Encrypt and send the compilation archive."""
        if not self.encryption_key:
            await self.negotiate_key()
        with open(archive_path, "rb") as f:
            archive_data = f.read()

        # Encrypt the archive before sending
        try:
            current_key = self.encryption_key
            if current_key is None:
                raise ValueError("Encryption key not negotiated")
            encrypted_data = encrypt_payload(archive_data, current_key)
        except Exception as e:
            logger.error("Encryption failed: %s", e)
            raise

        headers = {
            "Content-Type": "application/octet-stream",
            "X-Session-ID": str(self.session_id),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.endpoint}/api/compile",
                content=encrypted_data,
                headers=headers,
                timeout=300,
            )

            if response.status_code != 200:
                # Error response might also be encrypted or plain json
                try:
                    # Let's see if we can parse it as json
                    err_data = response.json()
                    detail = err_data.get("detail", response.text)
                except Exception:
                    # If not json, let's try decrypting it?
                    try:
                        current_key = self.encryption_key
                        if current_key is None:
                            raise ValueError(
                                "No encryption key available for decryption"
                            )
                        decrypted_err = decrypt_payload(response.content, current_key)
                        detail = decrypted_err.decode("utf-8")
                    except Exception:
                        detail = response.text

                raise RuntimeError(f"Server returned {response.status_code}: {detail}")

            # Response is encrypted
            return cast(bytes, response.content)

    async def decrypt_response(self, response_payload: bytes) -> bytes:
        """Decrypt the server response."""
        current_key = self.encryption_key
        if current_key is None:
            raise ValueError("Encryption key not negotiated")
        return decrypt_payload(response_payload, current_key)
