import io
import tarfile
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from scripts.backup_crypto import _extract_verified_tar, decrypt_directory, encrypt_directory


def test_encrypted_backup_roundtrip_hides_contents_and_names(tmp_path: Path):
    source = tmp_path / "staging"
    (source / "storage").mkdir(parents=True)
    (source / "database.dump").write_bytes(b"synthetic-auth-and-application-data")
    (source / "storage" / "private-certificate.pdf").write_bytes(b"synthetic-pdf-body")
    encrypted = tmp_path / "backup.cvault"
    restored = tmp_path / "restored"

    encrypt_directory(source, encrypted, "correct horse battery staple")

    data = encrypted.read_bytes()
    assert data.startswith(b"CVLTBK01")
    assert b"database.dump" not in data
    assert b"synthetic-auth-and-application-data" not in data
    decrypt_directory(encrypted, restored, "correct horse battery staple")
    assert (restored / "database.dump").read_bytes() == b"synthetic-auth-and-application-data"
    assert (restored / "storage" / "private-certificate.pdf").read_bytes() == b"synthetic-pdf-body"


def test_wrong_passphrase_and_tampered_bundle_fail_without_restore_output(tmp_path: Path):
    source = tmp_path / "staging"
    source.mkdir()
    (source / "fixture").write_bytes(b"not a real certificate")
    encrypted = tmp_path / "backup.cvault"
    encrypt_directory(source, encrypted, "correct horse battery staple")

    with pytest.raises(InvalidTag):
        decrypt_directory(encrypted, tmp_path / "wrong-passphrase", "incorrect passphrase value")

    changed = bytearray(encrypted.read_bytes())
    changed[-20] ^= 0x40
    tampered = tmp_path / "tampered.cvault"
    tampered.write_bytes(changed)
    destination = tmp_path / "tampered-output"
    with pytest.raises(InvalidTag):
        decrypt_directory(tampered, destination, "correct horse battery staple")
    assert not destination.exists()


def test_unsafe_tar_paths_are_rejected(tmp_path: Path):
    archive_path = tmp_path / "unsafe.tar"
    with tarfile.open(archive_path, "w") as archive:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 4
        archive.addfile(info, io.BytesIO(b"oops"))
    destination = tmp_path / "restore"

    with pytest.raises(ValueError, match="unsafe path"):
        _extract_verified_tar(archive_path, destination)
    assert not (tmp_path / "escape.txt").exists()
