import io
import tarfile

import pytest

import rgcc.core.security as security


@pytest.mark.parametrize(
    "flag",
    [
        "-Wall",
        "-O2",
        "-std=c++23",
        "-pthread",
        "-DDEBUG=1",
    ],
)
def test_safe_flags(flag):
    assert security.is_flag_safe(flag)


@pytest.mark.parametrize(
    "flag",
    [
        "-fplugin=evil.so",
        "-wrapper=/tmp/evil",
        "-B=/tmp/evil",
        "-specs=/tmp/x",
        "--specs=/tmp/x",
        "-load=evil",
        "-MF=/tmp/x",
        "-MT=/tmp/x",
        "-MQ=/tmp/x",
        "-MD",
        "-MMD",
        "-x=c",
        "-save-temps",
        "-fprofile-generate=/tmp/p",
        "-LOAD=x",
    ],
)
def test_dangerous_flags_are_rejected(flag):
    assert not security.is_flag_safe(flag)


def test_dangerous_prefixes_are_rejected_case_insensitively():
    assert not security.is_flag_safe("  -WRAPPER=evil")


def _make_tar(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tar:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                raw = content.encode()
                info.size = len(raw)
                tar.addfile(info, io.BytesIO(raw))
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = content
                tar.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = content
                tar.addfile(info)
    data.seek(0)
    return tarfile.open(fileobj=data, mode="r:")


def test_safe_extract_extracts_normal_file(tmp_path):
    with _make_tar([("a.txt", "hello", "file")]) as tar:
        security.safe_extract(tar, tmp_path)
    assert (tmp_path / "a.txt").read_text() == "hello"


def test_safe_extract_uses_data_filter_on_current_python(tmp_path, monkeypatch):
    called = {}

    class FakeTar:
        def extractall(self, *, path, filter):
            called.update(path=path, filter=filter)

    monkeypatch.setattr(security.tarfile, "data_filter", object(), raising=False)
    security.safe_extract(FakeTar(), tmp_path)
    assert called["path"] == tmp_path
    assert called["filter"] == "data"


def test_safe_extract_manual_branch_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.delattr(security.tarfile, "data_filter", raising=False)
    with _make_tar([("../evil.txt", "x", "file")]) as tar:
        with pytest.raises(PermissionError):
            security.safe_extract(tar, tmp_path)
    assert not (tmp_path.parent / "evil.txt").exists()


def test_safe_extract_manual_branch_rejects_symlink(tmp_path, monkeypatch):
    monkeypatch.delattr(security.tarfile, "data_filter", raising=False)
    with _make_tar([("link", "outside", "symlink")]) as tar:
        with pytest.raises(PermissionError):
            security.safe_extract(tar, tmp_path)


def test_safe_extract_manual_branch_rejects_hardlink(tmp_path, monkeypatch):
    monkeypatch.delattr(security.tarfile, "data_filter", raising=False)
    with _make_tar([("link", "other", "hardlink")]) as tar:
        with pytest.raises(PermissionError):
            security.safe_extract(tar, tmp_path)


def test_filter_safe_flags_keeps_safe_flags():
    flags = ["-Wall", "-O2", "-std=c++23"]

    result = security.filter_safe_flags(flags)

    assert result == flags


def test_filter_safe_flags_removes_inline_dangerous_flags():
    flags = [
        "-Wall",
        "-B=/evil",
        "-O2",
        "-specs=/tmp/evil.specs",
    ]

    result = security.filter_safe_flags(flags)

    assert result == ["-Wall", "-O2"]


def test_filter_safe_flags_removes_dangerous_flag_and_next_argument():
    flags = [
        "-Wall",
        "-B",
        "/evil/path",
        "-O2",
    ]

    result = security.filter_safe_flags(flags)

    assert result == ["-Wall", "-O2"]


def test_filter_safe_flags_removes_wrapper_and_its_argument():
    flags = [
        "-O2",
        "-wrapper",
        "/tmp/evil-wrapper",
        "-Wall",
    ]

    result = security.filter_safe_flags(flags)

    assert result == ["-O2", "-Wall"]


def test_filter_safe_flags_does_not_remove_next_argument_for_md():
    flags = [
        "-MD",
        "deps.d",
        "-Wall",
    ]

    result = security.filter_safe_flags(flags)

    assert result == ["deps.d", "-Wall"]


def test_safe_extract_manual_branch_extracts_normal_file(tmp_path, monkeypatch):
    monkeypatch.delattr(security.tarfile, "data_filter", raising=False)

    class FakeMember:
        name = "a.txt"

        def issym(self):
            return False

        def islnk(self):
            return False

    class FakeTar:
        def __init__(self):
            self.members = [FakeMember()]
            self.extracted = []

        def getmembers(self):
            return self.members

        def extract(self, member, *, path):
            self.extracted.append((member.name, path))

    tar = FakeTar()

    security.safe_extract(tar, tmp_path)

    assert tar.extracted == [("a.txt", tmp_path)]
