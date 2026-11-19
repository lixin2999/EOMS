"""文件：流式上传、鉴权下载、元数据与删除。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.response import ok
from app.api.serializers import file_brief
from app.core.deps import CurrentUser, DbSession, Scope, require_permission
from app.core.errors import ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.models.iam import SysFile
from app.services import storage

router = APIRouter(prefix="/files", tags=["文件中心"])

VIEW = Depends(require_permission("file:view"))
UPLOAD = Depends(require_permission("file:upload"))
DELETE = Depends(require_permission("file:delete"))


def _get_file(db, ctx: Scope, file_id: int) -> SysFile:
    item = db.get(SysFile, file_id)
    if item is None:
        raise NotFoundError("文件不存在")
    if item.company_id is not None and item.company_id != ctx.company_id and not ctx.is_super:
        raise NotFoundError("文件不存在或无权访问")
    return item


def _download_url(item: SysFile) -> str:
    return f"/api/v1/files/{item.id}/download"


def _row(item: SysFile) -> dict:
    data = file_brief(item)
    data["download_url"] = _download_url(item)
    data["hash"] = item.hash
    return data


@router.post("/upload", summary="上传文件（流式，单文件）", dependencies=[UPLOAD])
async def upload(
    db: DbSession,
    user: CurrentUser,
    ctx: Scope,
    file: UploadFile = File(..., description="待上传文件"),
    biz_type: str | None = Form(default=None),
    biz_id: int | None = Form(default=None),
) -> dict:
    if not file.filename:
        raise NotFoundError("请选择文件")
    stored = storage.save_stream(
        company_id=ctx.company_id,
        filename=file.filename,
        stream=file.file,
        content_type=file.content_type,
    )
    item = SysFile(
        company_id=ctx.company_id,
        biz_type=(biz_type or "")[:64] or None,
        biz_id=biz_id,
        name=file.filename[:255],
        path=stored.object_key,
        size=stored.size,
        hash=stored.sha256,
        mime=(file.content_type or "application/octet-stream")[:128],
        uploader_id=user.id,
    )
    db.add(item)
    db.flush()
    return ok(_row(item), "文件上传成功")


@router.get("", summary="文件列表", dependencies=[VIEW])
def list_files(
    db: DbSession,
    ctx: Scope,
    params: PageParams = Depends(),
    biz_type: str | None = None,
    biz_id: int | None = None,
    keyword: str | None = None,
    mine: bool = False,
) -> dict:
    stmt = select(SysFile).where(SysFile.company_id == ctx.company_id)
    if biz_type:
        stmt = stmt.where(SysFile.biz_type == biz_type)
    if biz_id:
        stmt = stmt.where(SysFile.biz_id == biz_id)
    if keyword:
        stmt = stmt.where(SysFile.name.like(f"%{keyword}%"))
    if mine:
        stmt = stmt.where(SysFile.uploader_id == ctx.user_id)
    from sqlalchemy import func

    total = int(
        db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    )
    rows = list(
        db.execute(stmt.order_by(SysFile.id.desc()).limit(params.page_size).offset(params.offset))
        .scalars()
        .all()
    )
    return ok(
        {
            "items": [_row(item) for item in rows],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
        }
    )


@router.get("/download", summary="按对象键下载（本地存储签名回退）", dependencies=[VIEW])
def download_by_key(
    db: DbSession,
    ctx: Scope,
    key: str = Query(..., min_length=3, max_length=512),
) -> StreamingResponse:
    if not ctx.is_super and not key.startswith(f"{ctx.company_id}/"):
        raise ForbiddenError("无权下载该文件")
    item = db.execute(
        select(SysFile)
        .where(SysFile.path == key, SysFile.company_id == ctx.company_id)
        .order_by(SysFile.id)
        .limit(1)
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("文件不存在")
    return _stream(item)


@router.get("/{file_id}", summary="文件元数据", dependencies=[VIEW])
def get_file(file_id: int, db: DbSession, ctx: Scope) -> dict:
    return ok(_row(_get_file(db, ctx, file_id)))


def _stream(item: SysFile) -> StreamingResponse:
    handle = storage.open_object(item.path)

    def iterator():
        try:
            while True:
                chunk = handle.read(1024 * 256)
                if not chunk:
                    break
                yield chunk
        finally:
            handle.close()

    filename = quote(item.name or "download")
    return StreamingResponse(
        iterator(),
        media_type=item.mime or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=file; filename*=UTF-8''{filename}",
            "Content-Length": str(item.size or 0),
        },
    )


@router.get("/{file_id}/download", summary="下载文件", dependencies=[VIEW])
def download(file_id: int, db: DbSession, ctx: Scope) -> StreamingResponse:
    item = _get_file(db, ctx, file_id)
    return _stream(item)


@router.delete("/{file_id}", summary="删除文件", dependencies=[DELETE])
def delete_file(file_id: int, db: DbSession, user: CurrentUser, ctx: Scope) -> dict:
    item = _get_file(db, ctx, file_id)
    if item.uploader_id != user.id and not ctx.is_super:
        raise ForbiddenError("只能删除本人上传的文件")
    path = item.path
    db.delete(item)
    db.flush()
    shared = db.execute(
        select(SysFile.id).where(SysFile.path == path).limit(1)
    ).first()
    if shared is None:
        storage.delete_object(path)
    return ok(None, "文件已删除")


@router.get(
    "/storage/health",
    summary="存储健康检查（管理员）",
    dependencies=[Depends(require_permission("system:config"))],
)
def storage_health() -> dict:
    return ok(storage.health())
