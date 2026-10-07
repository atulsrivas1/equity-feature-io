"""Stable-inode nonblocking cooperative local OS writer ownership."""
from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from typing import BinaryIO

from equity_feature_io_contracts.publication import SinkError, SinkErrorCode


class WriterLock:
    def __init__(self, path: Path) -> None:
        self.fd: int | None = None
        self._file: BinaryIO | None = None
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # File object also closes the descriptor if an unreachable owner is collected.
            # Explicit abort/close remains the supported deterministic lifetime boundary.
            self._file = os.fdopen(fd, "r+b", buffering=0)
            self.fd = fd
        except OSError as error:
            os.close(fd)
            code = SinkErrorCode.BUSY if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) else SinkErrorCode.UNAVAILABLE
            raise SinkError(code) from None
        except Exception:
            os.close(fd)
            raise

    def release(self) -> None:
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            assert self._file is not None
            self._file.close()
            self._file = None
