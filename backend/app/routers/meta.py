from fastapi import APIRouter, HTTPException
from ..cards import all_cards, get_card
from ..enemies import all_enemies
from .. import mapgen
from .. import forging

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/cards")
def cards():
    return all_cards()


@router.get("/forge-tree")
def forge_tree():
    """卡牌成长树静态定义（节点/前置/互斥组/价格），供前端渲染成长路线。"""
    return forging.public_tree()


@router.get("/enemies")
def enemies():
    return all_enemies()


@router.get("/map-preview")
def map_preview(seed: int = 12345):
    return mapgen.generate_map(seed)