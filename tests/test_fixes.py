"""Tests for fixes #18, #19, #21."""

import sys
import tempfile
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Issue #19 – Iterative BFS for include resolution
# ---------------------------------------------------------------------------
class TestIterativeIncludeResolution:
    """resolve_includes must not hit RecursionError on deep include trees."""

    def test_basic_include_chain(self, tmp_path: Path) -> None:
        """A simple chain of includes is fully resolved."""
        from rgcc.client.collect import resolve_includes

        # main.cpp -> a.h -> b.h -> c.h
        (tmp_path / "c.h").write_text("// bottom\n")
        (tmp_path / "b.h").write_text('#include "c.h"\n')
        (tmp_path / "a.h").write_text('#include "b.h"\n')
        (tmp_path / "main.cpp").write_text('#include "a.h"\nint main(){}\n')

        result = resolve_includes(tmp_path / "main.cpp", tmp_path, set())
        names = {p.name for p in result}
        assert names == {"main.cpp", "a.h", "b.h", "c.h"}

    def test_deep_tree_no_recursion_error(self, tmp_path: Path) -> None:
        """A 1500-level deep include chain must not raise RecursionError."""
        from rgcc.client.collect import resolve_includes

        depth = 1500
        # Create a chain: f0.h -> f1.h -> ... -> f1499.h
        for i in range(depth):
            (tmp_path / f"f{i}.h").write_text(f'#include "f{i + 1}.h"\n' if i < depth - 1 else "// leaf\n")

        result = resolve_includes(tmp_path / "f0.h", tmp_path, set())
        assert len(result) == depth

    def test_circular_dependency_no_infinite_loop(self, tmp_path: Path) -> None:
        """Circular includes must terminate."""
        from rgcc.client.collect import resolve_includes

        (tmp_path / "a.h").write_text('#include "b.h"\n')
        (tmp_path / "b.h").write_text('#include "a.h"\n')

        result = resolve_includes(tmp_path / "a.h", tmp_path, set())
        assert len(result) == 2

    def test_header_with_matching_source(self, tmp_path: Path) -> None:
        """When a .h is found, its matching .cpp is also included."""
        from rgcc.client.collect import resolve_includes

        (tmp_path / "util.h").write_text("void foo();\n")
        (tmp_path / "util.cpp").write_text('#include "util.h"\nvoid foo(){}\n')
        (tmp_path / "main.cpp").write_text('#include "util.h"\nint main(){}\n')

        result = resolve_includes(tmp_path / "main.cpp", tmp_path, set())
        names = {p.name for p in result}
        assert {"main.cpp", "util.h", "util.cpp"} <= names

    def test_missing_include_skipped(self, tmp_path: Path) -> None:
        """Missing includes (e.g. system headers) are silently skipped."""
        from rgcc.client.collect import resolve_includes

        (tmp_path / "main.cpp").write_text('#include <iostream>\n#include "nonexistent.h"\nint main(){}\n')

        result = resolve_includes(tmp_path / "main.cpp", tmp_path, set())
        names = {p.name for p in result}
        assert names == {"main.cpp"}

    def test_extra_include_dirs(self, tmp_path: Path) -> None:
        """-I directories are searched for angle-bracket includes."""
        from rgcc.client.collect import resolve_includes

        inc_dir = tmp_path / "include"
        inc_dir.mkdir()
        (inc_dir / "mylib.h").write_text("// mylib\n")
        (tmp_path / "main.cpp").write_text('#include <mylib.h>\nint main(){}\n')

        result = resolve_includes(tmp_path / "main.cpp", tmp_path, set(), [inc_dir])
        names = {p.name for p in result}
        assert "mylib.h" in names


# ---------------------------------------------------------------------------
# Issue #18 – Deterministic MASTER_TICKET_KEY
# ---------------------------------------------------------------------------
class TestDeterministicMasterTicketKey:
    """MASTER_TICKET_KEY must be deterministic across restarts."""

    def test_derive_key_is_deterministic(self) -> None:
        """Same AUTH_TOKEN + salt always produces the same key."""
        from rgcc.core.crypto import derive_key

        token = "test-token-12345"
        key1 = derive_key(token, salt=b"master_ticket_v1").hex()
        key2 = derive_key(token, salt=b"master_ticket_v1").hex()
        assert key1 == key2
        assert len(key1) == 64  # 32 bytes = 64 hex chars

    def test_different_tokens_produce_different_keys(self) -> None:
        """Different AUTH_TOKEN values must produce different keys."""
        from rgcc.core.crypto import derive_key

        key1 = derive_key("token-a", salt=b"master_ticket_v1").hex()
        key2 = derive_key("token-b", salt=b"master_ticket_v1").hex()
        assert key1 != key2

    def test_ticket_survives_key_reload(self) -> None:
        """A session ticket encrypted with one key can be decrypted with the
        same key derived fresh (simulating a server restart)."""
        from rgcc.core.crypto import decrypt_payload, derive_key, encrypt_payload

        token = "my-auth-token"
        key_hex = derive_key(token, salt=b"master_ticket_v1").hex()

        plaintext = b'{"key": "abc", "exp": 9999999999}'
        encrypted = encrypt_payload(plaintext, key_hex)

        # Simulate restart: derive the same key again
        key_hex_after_restart = derive_key(token, salt=b"master_ticket_v1").hex()
        decrypted = decrypt_payload(encrypted, key_hex_after_restart)
        assert decrypted == plaintext


# ---------------------------------------------------------------------------
# Issue #21 – Bounded JobStore
# ---------------------------------------------------------------------------
class TestJobStoreBounded:
    """JobStore must not grow indefinitely."""

    def test_capacity_limit_enforced(self) -> None:
        """Store evicts oldest entries when max_jobs is exceeded."""
        from rgcc.server.jobs.store import JobStore

        store = JobStore(max_jobs=5, ttl_seconds=99999)
        ids = []
        for _ in range(10):
            ids.append(store.create_job())

        assert len(store.jobs) == 5
        # Oldest 5 should have been evicted
        assert ids[0] not in store.jobs
        assert ids[4] not in store.jobs
        assert ids[5] in store.jobs
        assert ids[9] in store.jobs

    def test_ttl_eviction(self) -> None:
        """Expired entries are purged on create_job."""
        from rgcc.server.jobs.store import JobStore

        store = JobStore(max_jobs=999, ttl_seconds=1)

        # Create jobs
        old_id = store.create_job()
        assert len(store.jobs) == 1

        # Simulate time passing
        store.jobs[old_id].created_at = time.time() - 2  # 2 seconds ago

        # New create_job should purge the expired one
        new_id = store.create_job()
        assert old_id not in store.jobs
        assert new_id in store.jobs

    def test_update_and_get_job(self) -> None:
        """Basic CRUD still works correctly."""
        from rgcc.server.jobs.store import JobStore

        store = JobStore(max_jobs=10, ttl_seconds=60)
        job_id = store.create_job()

        store.update_job(job_id, "done", {"rc": 0}, "compiled ok")
        info = store.get_job(job_id)
        assert info is not None
        assert info.status == "done"
        assert info.manifest_result == {"rc": 0}
        assert info.logs == "compiled ok"

    def test_get_nonexistent_job(self) -> None:
        """get_job returns None for unknown IDs."""
        from rgcc.server.jobs.store import JobStore

        store = JobStore(max_jobs=10, ttl_seconds=60)
        assert store.get_job("nonexistent") is None
