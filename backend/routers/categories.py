from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.orm import Category
from models.schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.sort_order))
    rows = result.scalars().all()
    return _build_tree(rows)


@router.post("", response_model=CategoryOut)
async def create_category(body: CategoryCreate, db: AsyncSession = Depends(get_db)):
    cat = Category(name=body.name, parent_id=body.parent_id, sort_order=body.sort_order)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return _to_out(cat)


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(category_id: str, body: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    if body.name is not None:
        cat.name = body.name
    if body.parent_id is not None:
        cat.parent_id = body.parent_id
    if body.sort_order is not None:
        cat.sort_order = body.sort_order
    await db.commit()
    await db.refresh(cat)
    return _to_out(cat)


@router.delete("/{category_id}")
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    await db.delete(cat)
    await db.commit()
    return {"message": "已删除"}


def _to_out(cat: Category) -> CategoryOut:
    return CategoryOut(
        id=cat.id,
        name=cat.name,
        parent_id=cat.parent_id,
        sort_order=cat.sort_order,
        created_at=cat.created_at,
        children=[],
    )


def _build_tree(rows: list[Category]) -> list[CategoryOut]:
    node_map: dict[str, CategoryOut] = {}
    roots: list[CategoryOut] = []

    for r in rows:
        out = CategoryOut(
            id=r.id,
            name=r.name,
            parent_id=r.parent_id,
            sort_order=r.sort_order,
            created_at=r.created_at,
            children=[],
        )
        node_map[r.id] = out

    for r in rows:
        out = node_map[r.id]
        if out.parent_id and out.parent_id in node_map:
            node_map[out.parent_id].children.append(out)
        else:
            roots.append(out)

    return roots
