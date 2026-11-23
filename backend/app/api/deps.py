"""FastAPI 依赖：从 JWT 解析当前用户。"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import decode_token
from ..models import User

UNAUTHORIZED_MESSAGE = "未登录或登录已过期"


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_MESSAGE)

    payload = decode_token(authorization[7:])
    if not payload:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_MESSAGE)

    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_MESSAGE)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_MESSAGE)
    return user
