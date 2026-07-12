"""Password hashing and session helpers."""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt="phacostats-session")


def create_session_token(user_id: int) -> str:
    return _serializer().dumps({"user_id": user_id})


def decode_session_token(token: str) -> int | None:
    settings = get_settings()
    try:
        data = _serializer().loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    user_id = data.get("user_id")
    return int(user_id) if user_id is not None else None
