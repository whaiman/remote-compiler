import hashlib
import json
import tarfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

import rgcc.client.cli as cli
from rgcc.core.manifest import BuildManifest

runner = CliRunner()


def test_version_callback():
    with pytest.raises(cli.typer.Exit):
        cli._version_callback(True)


def test_callback_noop():
    assert cli.callback(None) is None


@pytest.mark.parametrize(
    ("path", "language"), [("main.cpp", "c++"), ("main.cc", "c++"), ("main.c", "c")]
)
def test_detect_language(path, language):
    assert cli._detect_language(Path(path)) == language


def test_detect_standard():
    assert cli._detect_standard("c") == "c17"
    assert cli._detect_standard("c++") == "c++23"


def test_available_standards():
    assert "c23" in cli._get_available_standards("c")
    assert "c++23" in cli._get_available_standards("c++")


def test_completions():
    assert cli.complete_platform("w") == ["win64"]
    ctx = Mock(params={"entry_point": "main.c"})
    assert "c17" in cli.complete_standard(ctx, "c1")
    assert cli.complete_standard(Mock(params={}), "c++2") == ["c++20", "c++23"]


def test_detect_compiler_and_platform():
    assert cli._detect_compiler(Path("a.cpp")) == "g++"
    assert cli._detect_compiler(Path("a.c")) == "gcc"
    with patch.object(cli._platform, "system", return_value="Linux"):
        assert cli._detect_platform() == "linux"


def test_detect_platform_unknown_os_falls_back_to_linux():
    with patch.object(cli._platform, "system", return_value="SomeUnknownOS"):
        assert cli._detect_platform() == "linux"


def test_parse_include_dirs_trailing_i(tmp_path):
    result = cli._parse_include_dirs_from_flags(
        ["-I"],
        tmp_path,
    )

    assert result == []


def test_output_name():
    assert cli._output_name("app", "linux") == "app"
    assert cli._output_name("app", "win64") == "app.exe"


def test_parse_include_dirs(tmp_path):
    good = tmp_path / "good"
    good.mkdir()
    other = tmp_path.parent / "outside"
    other.mkdir(exist_ok=True)
    result = cli._parse_include_dirs_from_flags(
        ["-Igood", "-I", "missing", "-I", ".", "-I" + str(other)], tmp_path
    )
    assert good.resolve() in result
    assert tmp_path.resolve() in result
    assert other.resolve() not in result


def test_resolve_project_root(tmp_path, monkeypatch):
    entry = tmp_path / "main.cpp"
    monkeypatch.chdir(tmp_path)
    assert cli._resolve_project_root(entry) == tmp_path
    outside = tmp_path.parent / "outside.cpp"
    assert cli._resolve_project_root(outside) == outside.parent


def test_load_manifest_missing(tmp_path):
    assert cli._load_manifest(tmp_path / "missing.json") is None


def test_load_manifest_valid(tmp_path):
    path = tmp_path / "build.json"
    path.write_text(BuildManifest().to_json())
    assert cli._load_manifest(path).standard == "c++23"


def test_load_manifest_invalid_exits(tmp_path):
    path = tmp_path / "build.json"
    path.write_text("{")
    with pytest.raises(cli.typer.Exit):
        cli._load_manifest(path)


def test_apply_cli_overrides():
    m = BuildManifest(flags=[])
    cli._apply_cli_overrides(
        m,
        entry_point=Path("main.cpp"),
        platform="win64",
        target="x86",
        sysroot="/sys",
        output="app",
        standard="c++20",
        compile_only=True,
        out_dir=Path("build"),
        save_logs=False,
        save_manifest_flag=False,
    )
    assert m.platform == "win64"
    assert m.target == "x86"
    assert m.sysroot == "/sys"
    assert m.standard == "c++20"
    assert m.output == "app.exe"
    assert "-c" in m.flags
    assert m.out_dir == "build"
    assert not m.save_logs and not m.save_manifest


def test_apply_cli_overrides_does_not_duplicate_c():
    m = BuildManifest(flags=["-c"])
    cli._apply_cli_overrides(
        m,
        entry_point=Path("main.cpp"),
        platform=None,
        target=None,
        sysroot=None,
        output=None,
        standard=None,
        compile_only=True,
        out_dir=Path("dist"),
        save_logs=True,
        save_manifest_flag=True,
    )
    assert m.flags.count("-c") == 1


def test_finalize_manifest(tmp_path):
    main = tmp_path / "main.cpp"
    main.write_text("hello")
    extra = tmp_path / "util.cpp"
    extra.write_text("")
    txt = tmp_path / "README"
    txt.write_text("")
    m = BuildManifest()
    cli._finalize_manifest(m, [main, extra, txt], tmp_path, main)
    assert m.sources == ["main.cpp", "util.cpp"]
    assert m.include_dirs == ["."]
    assert m.checksum_sha256 == hashlib.sha256(main.read_bytes()).hexdigest()
    assert m.timestamp


def test_build_archive(tmp_path):
    src = tmp_path / "main.cpp"
    src.write_text("int main(){}")
    work = tmp_path / "work"
    work.mkdir()
    path = cli._build_archive(
        work,
        [src],
        tmp_path,
        BuildManifest(entry_point="main.cpp", sources=["main.cpp"]),
    )
    with tarfile.open(path, "r:gz") as tar:
        assert set(tar.getnames()) == {"main.cpp", "build.json"}


def test_print_result_no_file(tmp_path):
    cli._print_result(tmp_path)


def test_print_result_success_and_failure(tmp_path):
    path = tmp_path / "manifest_result.json"
    path.write_text(json.dumps({"returncode": 0, "duration": 0.5}))
    cli._print_result(tmp_path)
    path.write_text(json.dumps({"returncode": 1, "duration": 0.5}))
    cli._print_result(tmp_path)


def test_cleanup_artifacts(tmp_path):
    (tmp_path / "compile.log").write_text("log")
    (tmp_path / "manifest_result.json").write_text("{}")
    cli._cleanup_artifacts(tmp_path, BuildManifest(save_logs=False, save_manifest=False))
    assert not (tmp_path / "compile.log").exists()
    assert not (tmp_path / "manifest_result.json").exists()


def test_cleanup_artifacts_keeps_requested_files(tmp_path):
    (tmp_path / "compile.log").write_text("log")
    (tmp_path / "manifest_result.json").write_text("{}")
    cli._cleanup_artifacts(tmp_path, BuildManifest(save_logs=True, save_manifest=True))
    assert (tmp_path / "compile.log").exists()
    assert (tmp_path / "manifest_result.json").exists()


def test_verify_buildinfo_missing_and_binary_missing(tmp_path, capsys):
    cli._verify_buildinfo(tmp_path, "app")
    (tmp_path / "buildinfo.json").write_text(json.dumps({"binary_hash": "x"}))
    cli._verify_buildinfo(tmp_path, "app")
    assert "not found" in capsys.readouterr().out


def test_verify_buildinfo_match_and_mismatch(tmp_path):
    binary = tmp_path / "app"
    binary.write_bytes(b"bin")
    good = hashlib.sha256(binary.read_bytes()).hexdigest()
    (tmp_path / "buildinfo.json").write_text(
        json.dumps({"binary_hash": good, "compiler_version": "gcc", "standard": "c++23"})
    )
    cli._verify_buildinfo(tmp_path, "app")
    (tmp_path / "buildinfo.json").write_text(json.dumps({"binary_hash": "bad"}))
    cli._verify_buildinfo(tmp_path, "app")


def test_verify_buildinfo_invalid_json(tmp_path):
    (tmp_path / "buildinfo.json").write_text("{")
    cli._verify_buildinfo(tmp_path, "app")


def test_interactive_cancel(monkeypatch, tmp_path):
    m = BuildManifest()
    answers = iter(["gcc", "c++23", "linux", "app", "dist", True, True, "-Wall", False])
    monkeypatch.setattr(cli.typer, "prompt", lambda *a, **k: next(answers))
    monkeypatch.setattr(cli.typer, "confirm", lambda *a, **k: next(answers))
    with pytest.raises(cli.typer.Exit):
        cli._run_interactive(m, tmp_path / "main.cpp", tmp_path / "build.json")


def test_interactive_save(monkeypatch, tmp_path):
    m = BuildManifest()

    prompts = iter(
        [
            "gcc",
            "c++23",
            "linux",
            "app",
            "dist",
            "-Wall",
        ]
    )

    confirmations = iter(
        [
            True,  # Save compilation logs?
            True,  # Save result manifest?
            True,  # Everything ready? Proceed?
            True,  # Save these settings?
        ]
    )

    monkeypatch.setattr(
        cli.typer,
        "prompt",
        lambda *args, **kwargs: next(prompts),
    )
    monkeypatch.setattr(
        cli.typer,
        "confirm",
        lambda *args, **kwargs: next(confirmations),
    )
    monkeypatch.setattr(
        m,
        "save_config",
        lambda path: path.write_text("{}"),
    )

    cli._run_interactive(
        m,
        tmp_path / "main.cpp",
        tmp_path / "build.json",
    )

    assert m.output == "app"
    assert m.flags == ["-Wall"]


def test_interactive_does_not_save(monkeypatch, tmp_path):
    m = BuildManifest()

    prompts = iter(
        [
            "gcc",
            "c++23",
            "linux",
            "app",
            "dist",
            "-Wall",
        ]
    )

    confirmations = iter(
        [
            True,  # save logs
            True,  # save manifest
            True,  # proceed
            False,  # save settings
        ]
    )

    monkeypatch.setattr(
        cli.typer,
        "prompt",
        lambda *args, **kwargs: next(prompts),
    )
    monkeypatch.setattr(
        cli.typer,
        "confirm",
        lambda *args, **kwargs: next(confirmations),
    )

    save_config = Mock()
    monkeypatch.setattr(m, "save_config", save_config)

    cli._run_interactive(
        m,
        tmp_path / "main.cpp",
        tmp_path / "build.json",
    )

    save_config.assert_not_called()


def test_interactive_save_failure_is_handled(monkeypatch, tmp_path):
    m = BuildManifest()

    prompts = iter(
        [
            "gcc",
            "c++23",
            "linux",
            "app",
            "dist",
            "-Wall",
        ]
    )

    confirmations = iter(
        [
            True,
            True,
            True,
            True,
        ]
    )

    monkeypatch.setattr(
        cli.typer,
        "prompt",
        lambda *args, **kwargs: next(prompts),
    )
    monkeypatch.setattr(
        cli.typer,
        "confirm",
        lambda *args, **kwargs: next(confirmations),
    )

    def fail_save(path):
        raise OSError("permission denied")

    monkeypatch.setattr(m, "save_config", fail_save)

    cli._run_interactive(
        m,
        tmp_path / "main.cpp",
        tmp_path / "build.json",
    )


def test_init_missing_file():
    result = runner.invoke(cli.app, ["init", "missing.cpp"])
    assert result.exit_code == 1


def test_init_existing_manifest_cancel(tmp_path, monkeypatch):
    main = tmp_path / "main.cpp"
    main.write_text("")

    manifest = BuildManifest()
    original = manifest.to_json()
    (tmp_path / "build.json").write_text(original)

    monkeypatch.chdir(tmp_path)

    runner.invoke(cli.app, ["init", str(main)], input="n\n")

    assert (tmp_path / "build.json").exists()
    assert (tmp_path / "build.json").read_text() == original


def test_compile_missing_file():
    result = runner.invoke(cli.app, ["compile", "missing.cpp"])
    assert result.exit_code == 1


def test_compile_dry_run(tmp_path, monkeypatch):
    main = tmp_path / "main.cpp"
    main.write_text("int main(){}")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["compile", str(main), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "Dry run complete" in result.stdout


def test_compile_invalid_config(tmp_path, monkeypatch):
    main = tmp_path / "main.cpp"
    main.write_text("int main(){}")

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        cli,
        "load_client_config",
        lambda: {
            "client": {
                "endpoint": "http://CHANGE_ME:4444",
                "auth_token": "PASTE_TOKEN_FROM_SERVER_CONFIG",
            }
        },
    )

    result = runner.invoke(cli.app, ["compile", str(main)])

    assert result.exit_code == 1
    assert "Missing or invalid configuration" in result.stdout


@pytest.mark.parametrize(
    "client_config",
    [
        {},
        {"endpoint": "http://localhost:4444"},
        {"auth_token": "token"},
        {
            "endpoint": "http://CHANGE_ME:4444",
            "auth_token": "token",
        },
        {
            "endpoint": "http://localhost:4444",
            "auth_token": "PASTE_TOKEN_FROM_SERVER_CONFIG",
        },
    ],
)
def test_compile_invalid_config_variants(
    tmp_path,
    monkeypatch,
    client_config,
):
    main = tmp_path / "main.cpp"
    main.write_text("int main(){}")

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        cli,
        "load_client_config",
        lambda: {"client": client_config},
    )

    result = runner.invoke(
        cli.app,
        ["compile", str(main)],
    )

    assert result.exit_code == 1
    assert "Missing or invalid configuration" in result.stdout


def test_compile_normal_flow_with_mocks(tmp_path, monkeypatch):
    main = tmp_path / "main.cpp"
    main.write_text("int main(){}")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rgcc.yaml").write_text(
        "client:\n  endpoint: http://localhost:4444\n  auth_token: token\n"
    )
    response_archive = tmp_path / "response.tar.gz"
    with tarfile.open(response_archive, "w:gz") as tar:
        data = b"{}"
        info = tarfile.TarInfo("manifest_result.json")
        info.size = len(data)
        tar.addfile(info, __import__("io").BytesIO(data))

    fake_client = Mock()
    fake_client.send_payload = Mock(return_value=b"encrypted")
    fake_client.decrypt_response = Mock(return_value=response_archive.read_bytes())
    monkeypatch.setattr(cli, "ApiClient", lambda *a, **k: fake_client)
    monkeypatch.setattr(cli, "safe_extract", lambda tar, path: tar.extractall(path=path))

    # Bypass asyncio.run with an identity wrapper for async mocks.
    async def send(_):
        return b"encrypted"

    async def decrypt(_):
        return response_archive.read_bytes()

    fake_client.send_payload = send
    fake_client.decrypt_response = decrypt
    result = runner.invoke(cli.app, ["compile", str(main), "--no-logs", "--no-manifest"])
    assert result.exit_code == 0, result.stdout
