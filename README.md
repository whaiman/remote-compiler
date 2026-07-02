# RGCC - Remote GCC Compiler System

Offload C/C++ builds from a resource-constrained device to a real machine. Encrypted end-to-end, single binary on each side, no daemon babysitting required.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Issues](https://img.shields.io/github/issues/whaiman/remote-compiler)](https://github.com/whaiman/remote-compiler/issues)
[![Last Commit](https://img.shields.io/github/last-commit/whaiman/remote-compiler)](https://github.com/whaiman/remote-compiler/commits/main)
[![Stars](https://img.shields.io/github/stars/whaiman/remote-compiler?style=social)](https://github.com/whaiman/remote-compiler/stargazers)

---

## Why this exists

Compiling C++ on a phone in Termux works, technically - until you hit a template-heavy header, `-O2` on a 2000-line file, and your battery drops 4% waiting for `g++`. RGCC started as a way to point `rgcc compile main.cpp` at a spare machine on the network and get a binary back a few seconds later, without setting up SSH, rsync, or a full remote dev environment.

It grew from there into a general-purpose remote compiler: manifest-driven builds, cross-compilation, reproducibility checks. But the core use case is still the original one - a thin client on a weak device, a build server on a strong one.

---

## Key Features

- **Unified package** - one `pip install` gives you both `rgcc` (client) and `rgccd` (server).
- **Manifest-driven builds** - full control over standard, defines, flags, and link targets via `build.json`.
- **Cross-compilation** - `--target` triples and `--sysroot` overrides for Linux/Windows/macOS targets.
- **Encrypted transport** - ECDH key exchange + AES-256-GCM for the payload (see [Security Model](#security-model) for what this does and doesn't protect against).
- **Reproducibility checks** - `--verify-reproducible` runs two independent builds and diffs the binary hash.
- **Shell autocompletion** - Bash, Zsh, Fish, PowerShell.

---

## How it works

1. `rgcc compile main.cpp` collects the source tree, generates a build manifest, and packs it into a tarball.
2. The client performs an ECDH handshake with the server (authenticated by a shared `auth_token`), deriving a session key.
3. The tarball is encrypted (AES-256-GCM) and uploaded.
4. The server validates the manifest, filters compiler/linker flags against a safety allowlist, and runs the actual compiler in a subprocess (no shell).
5. The resulting binary + logs + build info are packed, encrypted, and sent back.
6. The client decrypts and extracts the artifacts into `dist/`.

---

## Security Model

Read this before exposing the server beyond `localhost`.

**What is protected:**

- The build payload (source code, flags, resulting binary) is encrypted in transit with AES-256-GCM, keyed via an ECDH exchange tied to your `auth_token`.
- The server only executes a whitelisted set of compiler binaries (`gcc`, `g++`, `clang`, …), never an arbitrary path from the client.
- Compiler and linker flags are filtered against a list of known dangerous flags (`-B`, `-specs`, `-wrapper`, etc.) before being passed to the subprocess.
- Archive extraction on both ends is hardened against path traversal (Tar-slip).

**What is _not_ protected:**

- **There is no TLS and no server identity verification.** The ECDH handshake authenticates the session using the shared `auth_token`, but that token itself is sent as a bearer header during the handshake. An attacker who can position themselves on the network path (rogue AP, ARP spoofing, compromised router) can intercept the token and either read the handshake or man-in-the-middle the whole session.
- **This means "encrypted" here is not a substitute for TLS.** It protects against passive network logging (e.g., a nosy ISP or a shared network snooping traffic), not against an active attacker.
- The server has no built-in rate limiting. Don't expose it to the open internet without a reverse proxy in front that handles this.

**Practical guidance:**

| Deployment                             | Recommendation                                                                                                                           |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Same machine / `127.0.0.1` only        | Fine as-is.                                                                                                                              |
| Same trusted LAN (phone + home server) | Acceptable for most people. If your Wi-Fi isn't trusted, tunnel it (see below).                                                          |
| Different networks / over the internet | **Do not expose port 4444 directly.** Put it behind a TLS reverse proxy (Caddy, nginx) or a VPN/tunnel (WireGuard, Tailscale, `ssh -L`). |

Additional hardening:

- `rgccd.yaml` and `rgcc.yaml` contain the auth token in plaintext - the tool sets `chmod 600` on them automatically, but double-check on shared systems.
- Run the server container as a non-root user (the provided `Dockerfile.server` already does this) and drop capabilities: see the [Docker](#docker) section.
- This project has not undergone a formal third-party security audit. Treat it as solid for personal/trusted-network use, and apply the guidance above before anything more exposed.

---

## Installation

```bash
pip install "remote-compiler @ git+https://github.com/whaiman/remote-compiler.git"
```

Or for local development:

```bash
git clone https://github.com/whaiman/remote-compiler.git
cd remote-compiler
make install
```

---

## Quickstart

### 1. Build server

On the machine that will do the compiling, make sure `gcc`, `g++`, or `clang` is installed, then:

```bash
rgccd
```

On first run this generates `rgccd.yaml` with a random auth token (`chmod 600` applied automatically):

```yaml
server:
  auth_token: <auto-generated> # copy this to the client
  host: 0.0.0.0
  port: 4444
```

Override host/port if needed:

```bash
rgccd --host 127.0.0.1 --port 5000   # loopback only, no warning
rgccd --reload                        # dev mode, auto-restart
```

> If you bind to anything other than `127.0.0.1`/`localhost`, `rgccd` prints a warning reminding you that the handshake isn't TLS-authenticated. See [Security Model](#security-model).

### 2. Client

On the device you're compiling from (phone, laptop, whatever):

```yaml
# rgcc.yaml
client:
  endpoint: http://<server-ip>:4444
  auth_token: <paste-from-rgccd.yaml>
```

```bash
rgcc compile main.cpp
```

Your binary lands in `./dist/`.

---

## CLI Usage

```bash
# Basic compile, platform/standard auto-detected
rgcc compile main.cpp

# Custom output name and standard
rgcc compile main.cpp -o my_app --std c++20

# Cross-compile linux -> windows
rgcc compile main.cpp --target x86_64-w64-mingw32

# Custom sysroot for less common targets
rgcc compile main.cpp --target aarch64-linux-gnu --sysroot /usr/aarch64-linux-gnu

# Compile only, don't link
rgcc compile main.cpp --compile-only

# Pack and inspect the payload locally without sending it
rgcc compile main.cpp --dry-run

# Two independent remote builds, diff the output hash
rgcc compile main.cpp --verify-reproducible

# Interactive setup, saved to build.json
rgcc compile main.cpp -i
```

`build.json` (created via `rgcc init` or `-i`) persists your build configuration:

```json
{
  "compiler": "clang++",
  "standard": "c++20",
  "entry_point": "main.cpp",
  "output": "main.exe",
  "platform": "win64",
  "flags": ["-Wall", "-O3", "-static"],
  "defines": ["DEBUG=1"]
}
```

---

## Docker

`Dockerfile.server` builds a self-contained build daemon with GCC, Clang, and MinGW preinstalled, running as a non-root user.

```bash
make docker-build

# Create your server config first (see Quickstart), then:
docker run -d \
  --name rgcc-server \
  --read-only \
  --tmpfs /tmp \
  --cap-drop=ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 \
  --memory 2g \
  --cpus 2 \
  -p 127.0.0.1:4444:4444 \
  -v "$(pwd)/rgccd.yaml:/app/rgccd.yaml:ro" \
  rgcc-server:latest
```

Note the `-p 127.0.0.1:4444:4444` - this publishes the port on loopback only. Put a TLS reverse proxy in front if you need to reach it from elsewhere (see [Security Model](#security-model)).

To publish images to a registry (GHCR, Docker Hub, etc.), set up CI for it - this repository doesn't currently ship an automated build/publish workflow, so images have to be built locally with the command above until one is added.

---

## Development

```bash
git clone https://github.com/whaiman/remote-compiler.git
cd remote-compiler
make install-dev
make test
```

```text
make install         Install the unified package (-e .)
make install-dev      Install + dev tools (-e ".[dev]")
make dev-client       Dry-run compile of sample/main.cpp
make dev-server       Run server on 127.0.0.1:4444 (reload mode)
make docker-build      Build the server image
make docker-run-server Run the server container
make test             Run the test suite
make lint              ruff + black --check
make format             ruff format + fix
make clean               Remove build artifacts and caches
```

### Repository structure

```text
remote-compiler/
├── rgcc/
│   ├── core/       # crypto, config, manifest, checksum
│   ├── client/     # CLI, source collection, transport
│   └── server/     # HTTP daemon, compiler runner, job store
├── pyproject.toml
└── Makefile
```

---

## Contributing

PRs welcome. For anything touching `rgcc/core/security.py`, `rgcc/server/compiler/runner.py`, or the crypto/auth path, please open an issue first to discuss before submitting - that's the code where a mistake actually matters.

1. Fork the repo
2. `git checkout -b feature/your-thing`
3. `make test && make lint`
4. Open a PR describing what changed and why

## License

AGPL-3.0. Modified versions - including ones run as a network service - must also release their source. See [LICENSE](LICENSE).
