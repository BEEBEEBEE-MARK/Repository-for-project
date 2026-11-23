"""ORM 模型（表结构见 开发文档/数据库设计.md v1.2）。"""

from .invite import InviteCode
from .travel_record import TravelRecord
from .user import User

__all__ = ["User", "InviteCode", "TravelRecord"]
