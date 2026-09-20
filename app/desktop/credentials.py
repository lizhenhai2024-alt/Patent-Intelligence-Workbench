"""Secure credential storage for desktop provider settings.

Windows uses Credential Manager directly through Win32 CredRead/CredWrite.
Other platforms remain environment-variable only in V1.
"""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from typing import Protocol

EPO_TARGET = "PatentIntelligenceWorkbench/EPO_OPS"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


@dataclass(frozen=True, slots=True)
class EpoOpsCredentials:
    consumer_key: str
    consumer_secret: str
    source: str


class CredentialStore(Protocol):
    @property
    def persistent_available(self) -> bool:
        ...

    def load_epo_ops(self) -> EpoOpsCredentials | None:
        ...

    def save_epo_ops(self, consumer_key: str, consumer_secret: str) -> None:
        ...

    def delete_epo_ops(self) -> None:
        ...


class EnvironmentCredentialStore:
    @property
    def persistent_available(self) -> bool:
        return False

    def load_epo_ops(self) -> EpoOpsCredentials | None:
        key = os.getenv("EPO_OPS_KEY")
        secret = os.getenv("EPO_OPS_SECRET")
        if not key or not secret:
            return None
        return EpoOpsCredentials(
            consumer_key=key,
            consumer_secret=secret,
            source="environment",
        )

    def save_epo_ops(self, consumer_key: str, consumer_secret: str) -> None:
        raise RuntimeError(
            "Persistent credential storage is only available on Windows in V1."
        )

    def delete_epo_ops(self) -> None:
        return None


class WindowsCredentialStore:
    @property
    def persistent_available(self) -> bool:
        return os.name == "nt"

    def load_epo_ops(self) -> EpoOpsCredentials | None:
        if os.name != "nt":
            return None
        record = _windows_read_generic(EPO_TARGET)
        if record is None:
            return None
        username, secret = record
        if not username or not secret:
            return None
        return EpoOpsCredentials(
            consumer_key=username,
            consumer_secret=secret,
            source="windows-credential-manager",
        )

    def save_epo_ops(self, consumer_key: str, consumer_secret: str) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows Credential Manager is unavailable.")
        key = consumer_key.strip()
        secret = consumer_secret.strip()
        if not key or not secret:
            raise ValueError("EPO consumer key and secret are required.")
        _windows_write_generic(EPO_TARGET, key, secret)

    def delete_epo_ops(self) -> None:
        if os.name != "nt":
            return
        _windows_delete_generic(EPO_TARGET)


class DesktopCredentialStore:
    """Windows Credential Manager with environment-variable fallback."""

    def __init__(self) -> None:
        self.windows = WindowsCredentialStore()
        self.environment = EnvironmentCredentialStore()

    @property
    def persistent_available(self) -> bool:
        return self.windows.persistent_available

    def load_epo_ops(self) -> EpoOpsCredentials | None:
        return self.windows.load_epo_ops() or self.environment.load_epo_ops()

    def save_epo_ops(self, consumer_key: str, consumer_secret: str) -> None:
        self.windows.save_epo_ops(consumer_key, consumer_secret)

    def delete_epo_ops(self) -> None:
        self.windows.delete_epo_ops()


def _windows_read_generic(target: str) -> tuple[str, str] | None:
    from ctypes import wintypes

    class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
        _fields_ = [
            ("Keyword", wintypes.LPWSTR),
            ("Flags", wintypes.DWORD),
            ("ValueSize", wintypes.DWORD),
            ("Value", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    credential_pointer = ctypes.POINTER(CREDENTIALW)()
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    cred_read = advapi32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    cred_read.restype = wintypes.BOOL
    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]

    if not cred_read(
        target,
        CRED_TYPE_GENERIC,
        0,
        ctypes.byref(credential_pointer),
    ):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return None
        raise OSError(error, "CredReadW failed")

    try:
        credential = credential_pointer.contents
        blob = ctypes.string_at(
            credential.CredentialBlob,
            credential.CredentialBlobSize,
        )
        secret = blob.decode("utf-16-le")
        return credential.UserName or "", secret
    finally:
        cred_free(credential_pointer)


def _windows_write_generic(target: str, username: str, secret: str) -> None:
    from ctypes import wintypes

    class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
        _fields_ = [
            ("Keyword", wintypes.LPWSTR),
            ("Flags", wintypes.DWORD),
            ("ValueSize", wintypes.DWORD),
            ("Value", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    secret_bytes = secret.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(secret_bytes)).from_buffer_copy(secret_bytes)

    credential = CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(secret_bytes)
    credential.CredentialBlob = ctypes.cast(
        blob,
        ctypes.POINTER(ctypes.c_ubyte),
    )
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = username

    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    cred_write = advapi32.CredWriteW
    cred_write.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    cred_write.restype = wintypes.BOOL

    if not cred_write(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise OSError(error, "CredWriteW failed")


def _windows_delete_generic(target: str) -> None:
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    cred_delete = advapi32.CredDeleteW
    cred_delete.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    cred_delete.restype = wintypes.BOOL

    if not cred_delete(target, CRED_TYPE_GENERIC, 0):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return
        raise OSError(error, "CredDeleteW failed")
