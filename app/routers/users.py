from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.models import db, User
from typing import List

router = APIRouter(prefix="/users")


class UserForm(BaseModel):
    name: str
    username: str
    email: str


@router.get("/")
async def list_users() -> List[User]:
    return [User(**user) for user in db.users.find()]


@router.post("/")
async def create_user(user: UserForm) -> Response:
    ret = db.users.insert_one(user.dict(by_alias=True))
    return Response()
