from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from acgn_assistant.db import get_session
from acgn_assistant.models.resource import Resource, ResourceCreate, ResourceTagLink, ResourceUpdate, Tag
from acgn_assistant.routers.deps import get_current_admin_user, get_current_user
from acgn_assistant.core.time import utcnow

router = APIRouter(prefix="/resources", tags=["resources"])


def _get_or_create_tag(session: Session, name: str) -> Tag:
    tag = session.exec(select(Tag).where(Tag.name == name)).first()
    if tag:
        return tag
    tag = Tag(name=name)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


@router.get("", response_model=list[Resource])
def list_resources(
    tag: str | None = None,
    session: Session = Depends(get_session),
    _user=Depends(get_current_user),
):
    stmt = select(Resource).where(Resource.deleted_at.is_(None)).where(Resource.is_active.is_(True))
    if tag:
        # 通过关联表筛选
        stmt = (
            select(Resource)
            .join(ResourceTagLink, ResourceTagLink.resource_id == Resource.id)
            .join(Tag, Tag.id == ResourceTagLink.tag_id)
            .where(Resource.deleted_at.is_(None))
            .where(Resource.is_active.is_(True))
            .where(Tag.name == tag)
        )
    return list(session.exec(stmt.order_by(Resource.created_at.desc())))


@router.post("", response_model=Resource)
def create_resource(
    payload: ResourceCreate,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    r = Resource(
        resource_type=payload.resource_type,
        title=payload.title,
        url=payload.url,
        content=payload.content,
    )
    session.add(r)
    session.commit()
    session.refresh(r)

    # 绑定 tags
    for name in payload.tag_names or []:
        t = _get_or_create_tag(session, name)
        session.add(ResourceTagLink(resource_id=r.id, tag_id=t.id))
    session.commit()

    return r


@router.put("/{resource_id}", response_model=Resource)
def update_resource(
    resource_id: str,
    payload: ResourceUpdate,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    r = session.get(Resource, resource_id)
    if not r or r.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

    if payload.resource_type is not None:
        r.resource_type = payload.resource_type
    if payload.title is not None:
        r.title = payload.title
    if payload.url is not None:
        r.url = payload.url
    if payload.content is not None:
        r.content = payload.content
    if payload.is_active is not None:
        r.is_active = payload.is_active
    r.updated_at = utcnow()

    session.add(r)
    session.commit()

    if payload.tag_names is not None:
        # 清空旧关联
        links = session.exec(select(ResourceTagLink).where(ResourceTagLink.resource_id == r.id)).all()
        for l in links:
            session.delete(l)
        session.commit()
        for name in payload.tag_names:
            t = _get_or_create_tag(session, name)
            session.add(ResourceTagLink(resource_id=r.id, tag_id=t.id))
        session.commit()

    session.refresh(r)
    return r


@router.delete("/{resource_id}")
def soft_delete_resource(
    resource_id: str,
    session: Session = Depends(get_session),
    _admin=Depends(get_current_admin_user),
):
    r = session.get(Resource, resource_id)
    if not r or r.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

    r.deleted_at = utcnow()
    r.updated_at = utcnow()
    session.add(r)
    session.commit()
    return {"deleted": True}
