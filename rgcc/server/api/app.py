import json
import logging
import os
import shutil
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rgcc.core.config import load_server_config
from rgcc.core.crypto import (
    compute_shared_key,
    decrypt_payload,
    encrypt_payload,
    generate_ec_keypair,
)
from rgcc.core.manifest import BuildManifest
from rgcc.core.security import safe_extract
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from rgcc.server.compiler.fallback import run_fallback_compilation
from rgcc.server.compiler.runner import run_compilation
from rgcc.server.jobs.store import job_store

# 1. Initialize App and Logger first so we can use them
logger = logging.getLogger("rgcc")

# 2. Load configuration
CFG = load_server_config()
SERVER_CFG = CFG.get("server", {})
AUTH_TOKEN = SERVER_CFG.get("auth_token")

if not AUTH_TOKEN:
    logger.error("Configuration error: 'auth_token' missing in server_config.yaml")
    raise RuntimeError("Missing required configuration keys.")

# Single server runtime master key for encrypting transient Session Tickets
MASTER_TICKET_KEY = os.urandom(32).hex()


@dataclass
class HandshakeRequest:
    public_key: str


@dataclass
class HandshakeResponse:
    public_key: str
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def handshake(request: Request) -> Response:
    try:
        data = await request.json()
        req = HandshakeRequest(**data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Invalid handshake request: {e}")
        return JSONResponse(
            {"detail": "Invalid request body or missing fields"}, status_code=400
        )

    priv, pub = generate_ec_keypair()
    aes_key = compute_shared_key(priv, req.public_key, AUTH_TOKEN)

    ticket_payload = json.dumps({"key": aes_key, "exp": time.time() + 60}).encode(
        "utf-8"
    )
    session_id = encrypt_payload(ticket_payload, MASTER_TICKET_KEY).hex()

    resp = HandshakeResponse(public_key=pub, session_id=session_id)
    return JSONResponse(asdict(resp))


async def compile(request: Request) -> Response:
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return JSONResponse({"detail": "Missing session ID"}, status_code=400)

    try:
        # Decrypt ticket
        ticket_payload = decrypt_payload(bytes.fromhex(session_id), MASTER_TICKET_KEY)
        ticket_data = json.loads(ticket_payload.decode("utf-8"))

        # Check expiration (60 second TTL mitigates replay attacks)
        if time.time() > ticket_data["exp"]:
            return JSONResponse({"detail": "Ticket expired"}, status_code=401)

        encryption_key = ticket_data["key"]
    except Exception as e:
        logger.warning(f"Invalid session check: {e}")
        return JSONResponse({"detail": "Invalid session ticket"}, status_code=401)
    body = await request.body()

    # 1. Decrypt payload
    try:
        decrypted_data = decrypt_payload(body, encryption_key)
    except Exception as e:
        logger.error("Decryption failed: %s", e)
        return JSONResponse({"detail": "Failed to decrypt payload"}, status_code=400)

    # 2. Extract archive
    work_dir = Path(tempfile.mkdtemp(prefix="rgcc_server_"))
    try:
        archive_path = work_dir / "request.tar.gz"
        with open(archive_path, "wb") as archive_file:
            archive_file.write(decrypted_data)

        src_dir = work_dir / "src"
        src_dir.mkdir()

        with tarfile.open(archive_path, "r:gz") as tar:
            safe_extract(tar, src_dir)

        src_files = []
        for root, _, current_files in os.walk(src_dir):
            for filename in current_files:
                p = Path(root) / filename
                src_files.append(p.as_posix())

        # 3. Load manifest
        manifest_path = src_dir / "build.json"

        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest_dict = json.load(manifest_file)
                manifest = BuildManifest.from_dict(manifest_dict)
                comp_result = run_compilation(manifest, work_dir, config=CFG)
        else:
            sources = list(src_dir.glob("*.cpp")) or list(src_dir.glob("*.c"))
            if not sources:
                return JSONResponse(
                    {"detail": "No source files found"}, status_code=400
                )
            comp_result = run_fallback_compilation(sources[0], work_dir / "a.out")

        # 4. Update job store
        job_id = job_store.create_job()
        manifest_res = {
            "returncode": comp_result.returncode,
            "duration": comp_result.duration,
            "job_id": job_id,
        }
        job_store.update_job(
            job_id,
            "done" if comp_result.returncode == 0 else "failed",
            manifest_res,
            comp_result.stdout + comp_result.stderr,
        )

        # 5. Pack Response
        response_archive_path = work_dir / "response.tar.gz"
        with tarfile.open(response_archive_path, "w:gz") as tar:
            log_path = work_dir / "compile.log"
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write(comp_result.stdout)
                log_file.write("\n--- stderr ---\n")
                log_file.write(comp_result.stderr)
            tar.add(log_path, arcname="compile.log")

            res_json_path = work_dir / "manifest_result.json"
            with open(res_json_path, "w", encoding="utf-8") as res_file:
                json.dump(manifest_res, res_file)
            tar.add(res_json_path, arcname="manifest_result.json")

            if comp_result.output_path and comp_result.output_path.exists():
                tar.add(comp_result.output_path, arcname=comp_result.output_path.name)

        # 6. Encrypt Response
        with open(response_archive_path, "rb") as response_file:
            response_data = response_file.read()
        encrypted_resp = encrypt_payload(response_data, encryption_key)

        return Response(
            content=encrypted_resp,
            media_type="application/octet-stream",
            background=BackgroundTask(shutil.rmtree, work_dir, True),
        )

    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.exception("Unexpected error: %s", e)
        return JSONResponse({"detail": str(e)}, status_code=500)


async def health(request: Request) -> Response:
    return JSONResponse({"status": "OK"})


routes = [
    Route("/api/compile", compile, methods=["POST"]),
    Route("/api/handshake", handshake, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
]

app = Starlette(routes=routes)
