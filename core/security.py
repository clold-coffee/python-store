from datetime import timedelta, datetime, timezone

import jwt
from pwdlib import PasswordHash


from core.config import get_settings

password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)

def create_access_token(subject: str, expires_delta: timedelta = None) -> str:
    setting = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + (expires_delta or timedelta(minutes= setting.access_token_expire_minutes))


    # jwt 内容
    payload = {
        'exp': expires_at,
        'iat': now,
        'sub': subject,
        'scope': setting.app_v1_prefix,
        "type": "access",
    }


    return jwt.encode(
        payload,
        setting.secret_key,
        algorithm=setting.jwt_algorithm,
    )



def decode_token(token: str) -> dict[str, object]:
    setting = get_settings()
    return jwt.decode(
        token,
        setting.secret_key,
        algorithms=[setting.jwt_algorithm]
    )

