"""Create/verify encrypted CertVault backup bundles with a local passphrase.

The bundle is a streaming tar encrypted with AES-256-GCM. This tool never takes
the passphrase on the command line and never prints bundle member names.
"""

from __future__ import annotations

import argparse
import getpass
import io
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"CVLTBK01"
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
HEADER_BYTES = len(MAGIC) + SALT_BYTES + NONCE_BYTES
CHUNK_BYTES = 1024 * 1024
SCRYPT_N = 2**14


class EncryptingWriter:
    def __init__(self, output: io.BufferedWriter, encryptor) -> None:
        self.output = output
        self.encryptor = encryptor
        self.position = 0

    def write(self, data: bytes) -> int:
        self.output.write(self.encryptor.update(data))
        self.position += len(data)
        return len(data)

    def tell(self) -> int:
        return self.position

    def flush(self) -> None:
        self.output.flush()


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt_directory(source: Path, output: Path, passphrase: str) -> None:
    source = source.resolve(strict=True)
    output = output.resolve()
    if not source.is_dir() or source == output or source in output.parents:
        raise ValueError("Output must be outside a valid source directory")
    if output.exists():
        raise FileExistsError("Encrypted backup already exists; choose a new output name")
    output.parent.mkdir(parents=True, exist_ok=True)
    members = sorted(source.rglob("*"))
    if any(item.is_symlink() for item in members):
        raise ValueError("Backup source cannot contain symbolic links")
    files = [item for item in members if item.is_file()]
    if not files:
        raise ValueError("Backup source contains no files")

    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    header = MAGIC + salt + nonce
    encryptor = Cipher(algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    try:
        with output.open("xb") as raw:
            raw.write(header)
            stream = EncryptingWriter(raw, encryptor)
            with tarfile.open(fileobj=stream, mode="w|") as archive:
                for path in files:
                    archive.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
            raw.write(encryptor.finalize())
            raw.write(encryptor.tag)
            raw.flush()
            os.fsync(raw.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def _extract_verified_tar(tar_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve(strict=True)
    try:
        with tarfile.open(tar_path, mode="r:") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if (
                    name.is_absolute()
                    or "\\" in member.name
                    or ":" in member.name
                    or any(part in ("", ".", "..") for part in name.parts)
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError("Backup archive contains an unsafe path or file type")
                target = root.joinpath(*name.parts)
                if not target.resolve().is_relative_to(root):
                    raise ValueError("Backup archive path escapes the restore directory")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Backup archive contains an unreadable file")
                with source, target.open("xb") as result:
                    shutil.copyfileobj(source, result, CHUNK_BYTES)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def decrypt_directory(source: Path, destination: Path, passphrase: str) -> None:
    if destination.exists():
        raise FileExistsError("Restore directory already exists; choose an empty new path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = source.stat().st_size
    if size < HEADER_BYTES + TAG_BYTES:
        raise ValueError("Encrypted backup is truncated")
    with source.open("rb") as encrypted:
        header = encrypted.read(HEADER_BYTES)
        if len(header) != HEADER_BYTES or header[: len(MAGIC)] != MAGIC:
            raise ValueError("File is not a CertVault encrypted backup")
        salt_start = len(MAGIC)
        salt = header[salt_start : salt_start + SALT_BYTES]
        nonce = header[salt_start + SALT_BYTES :]
        encrypted.seek(-TAG_BYTES, os.SEEK_END)
        tag = encrypted.read(TAG_BYTES)
        encrypted.seek(HEADER_BYTES)
        remaining = size - HEADER_BYTES - TAG_BYTES
        decryptor = Cipher(
            algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce, tag)
        ).decryptor()
        decryptor.authenticate_additional_data(header)
        fd, plaintext_name = tempfile.mkstemp(
            prefix="certvault-verified-", suffix=".tar", dir=destination.parent
        )
        plaintext = Path(plaintext_name)
        try:
            with os.fdopen(fd, "wb") as clear:
                while remaining:
                    block = encrypted.read(min(CHUNK_BYTES, remaining))
                    if not block:
                        raise ValueError("Encrypted backup is truncated")
                    remaining -= len(block)
                    clear.write(decryptor.update(block))
                clear.write(decryptor.finalize())  # GCM tag validation before extraction.
                clear.flush()
                os.fsync(clear.fileno())
            _extract_verified_tar(plaintext, destination)
        except BaseException:
            if plaintext.exists():
                plaintext.unlink()
            raise
        finally:
            plaintext.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    enc = subparsers.add_parser("encrypt")
    enc.add_argument("--source", type=Path, required=True)
    enc.add_argument("--output", type=Path, required=True)
    dec = subparsers.add_parser("decrypt")
    dec.add_argument("--input", type=Path, required=True)
    dec.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    if args.action == "encrypt":
        password = getpass.getpass("Backup encryption passphrase (16+ characters): ")
        if len(password) < 16:
            parser.error("Passphrase must contain at least 16 characters")
        if password != getpass.getpass("Confirm backup encryption passphrase: "):
            parser.error("Passphrases do not match")
        encrypt_directory(args.source, args.output, password)
    else:
        password = getpass.getpass("Backup decryption passphrase: ")
        decrypt_directory(args.input, args.destination, password)
    print(
        "Encrypted backup written."
        if args.action == "encrypt"
        else "Backup authenticated and extracted."
    )


if __name__ == "__main__":
    main()
