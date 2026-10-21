import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError

_password_hasher = PasswordHasher()
_dummy_password_hash = _password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHash, VerificationError):
        return False


def verify_unknown_user_password(password: str) -> None:
    verify_password(_dummy_password_hash, password)
