# Input: /folders 下的查询、创建、删除请求  |  Output: FolderRead 列表/单项响应与状态码
# Output: 暴露文件夹 CRUD，并在删除时执行“迁移牌组到默认文件夹”的规则
# Role: 这是 library 左列文件夹管理的直接 HTTP 入口
# Use: 默认文件夹 id=1 受保护；若后续抽 service，可保持这里作为薄路由层
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.dependencies import get_deck_service
from app.db.models import Deck, Folder
from app.db.session import get_session
from app.services.deck_service import DeckService

router = APIRouter(prefix="/folders", tags=["folders"])


class FolderCreate(BaseModel):
    name: str


class FolderRead(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class FolderUpdate(BaseModel):
    name: str


@router.get("", response_model=list[FolderRead])
def list_folders(session: Session = Depends(get_session)) -> list[FolderRead]:
    return [FolderRead.model_validate(f) for f in session.exec(select(Folder)).all()]


@router.post("", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
def create_folder(payload: FolderCreate, session: Session = Depends(get_session)) -> FolderRead:
    if session.exec(select(Folder).where(Folder.name == payload.name)).first():
        raise HTTPException(status_code=409, detail="同名文件夹已存在")
    folder = Folder(name=payload.name)
    session.add(folder)
    session.commit()
    session.refresh(folder)
    return FolderRead.model_validate(folder)


@router.put("/{folder_id}", response_model=FolderRead)
def update_folder(folder_id: int, payload: FolderUpdate, session: Session = Depends(get_session)) -> FolderRead:
    if folder_id == 1:
        raise HTTPException(status_code=400, detail="Cannot rename default folder")
    folder = session.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    duplicate = session.exec(select(Folder).where(Folder.name == payload.name, Folder.id != folder_id)).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Folder name already exists")
    folder.name = payload.name
    session.add(folder)
    session.commit()
    session.refresh(folder)
    return FolderRead.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: int,
    session: Session = Depends(get_session),
    deck_service: DeckService = Depends(get_deck_service),
) -> None:
    folder = session.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder_id == 1:
        raise HTTPException(status_code=400, detail="Cannot delete default folder")
    decks = session.exec(select(Deck).where(Deck.folder_id == folder_id)).all()
    for deck in decks:
        deck_service.delete_deck_record(session, deck)
    session.delete(folder)
    session.commit()
