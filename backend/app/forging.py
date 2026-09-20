from __future__ import annotations

# 卡牌成长树：在锻造节点花金币为“指定卡牌实例”解锁成长节点。
# 同名卡的每张副本是独立实例（uid），各自保存已解锁节点（growth）与累计花费
# （growth_cost）；成长节点带前置条件（requires）与互斥分组（mutex_group：
# 同组最多选一个，选其一即锁定另一条）。引擎在战斗中按实例的 growth 把基础
# 卡牌定义即时换算为“生效卡牌”，因此成长自动贯通战斗/商店移除/跨章继承/续局/回放。
#
# 成长树（三系主干，锋锐系第二层互斥）：
#
#   sharpen 锋锐 ─┬─ edge 开刃（与 bulwark 互斥）─ annihilator 歼灭（终式）
#                 └─ bulwark 坚壁（与 edge 互斥）─ fortify 金城（终式）
#   empower 强效 ─┬─ overload 过载 ─ transcendent 超凡（终式）
#                 └─ resonance 共鸣 ─ momentum 乘势（终式）
#   refine 精炼 ──┬─ flux 流转 ──── frugality 俭用（终式）
#                 └─ inspiration 灵感 ─ insight 洞见（终式）
#
# 历史兼容：2.3.0 之前实例只有扁平的 forges:[分支…]（同分支可叠加、分支可混选），
# 迁移时逐条映射为等价的迁移专用节点（id 以 "~" 开头，只在旧档迁移时产生，
# 正常成长不可选、不占互斥位），换算结果与旧规则逐值一致。

# 一次成长的默认金币花费（Tier-1 节点）；更深层节点在节点定义里自带 cost
FORGE_COST = 25

# 互斥组 id -> 人类说明（同组节点最多解锁一个；解锁组内任一则其余锁定）
MUTEX_GROUPS = {
    "edge_or_bulwark": "开刃与坚壁互斥：该牌只能选择攻势或守势一路",
}

# 成长节点定义（数据驱动；实际换算见 effective_card）
# tier: 1 主干 / 2 深层 / 3 终式
# requires: 前置节点 id 列表（须全部已解锁）
# mutex_group: 互斥组（同组只能存在一个）
FORGE_NODES = [
    # ---------- Tier-1 主干 ----------
    {"id": "sharpen", "name": "锋锐", "tag": "锋", "tier": 1, "cost": 25,
     "requires": [], "mutex_group": None,
     "desc": "所有攻击伤害 +3；若该牌没有攻击效果，则格挡 +3。"},
    {"id": "empower", "name": "强效", "tag": "强", "tier": 1, "cost": 25,
     "requires": [], "mutex_group": None,
     "desc": "非攻击数值（状态层数/抽牌/回复/能量）+1；若没有此类效果，攻击伤害 +2。"},
    {"id": "refine", "name": "精炼", "tag": "炼", "tier": 1, "cost": 25,
     "requires": [], "mutex_group": None,
     "desc": "消耗 -1（最低 0）。"},
    # ---------- Tier-2 锋锐系（互斥分支） ----------
    {"id": "edge", "name": "开刃", "tag": "刃", "tier": 2, "cost": 50,
     "requires": ["sharpen"], "mutex_group": "edge_or_bulwark",
     "desc": "所有攻击伤害再 +3；无攻击效果的牌改为格挡再 +3。（与坚壁互斥）"},
    {"id": "bulwark", "name": "坚壁", "tag": "壁", "tier": 2, "cost": 50,
     "requires": ["sharpen"], "mutex_group": "edge_or_bulwark",
     "desc": "所有格挡再 +5；没有格挡效果的牌改为获得 5 点格挡。（与开刃互斥）"},
    # ---------- Tier-2 强效系 ----------
    {"id": "overload", "name": "过载", "tag": "载", "tier": 2, "cost": 50,
     "requires": ["empower"], "mutex_group": None,
     "desc": "非攻击数值再 +2；若没有此类效果，攻击伤害 +3。"},
    {"id": "resonance", "name": "共鸣", "tag": "鸣", "tier": 2, "cost": 50,
     "requires": ["empower"], "mutex_group": None,
     "desc": "本回合打出的第一张攻击牌伤害 +4；该牌不是攻击牌时此成长不生效。"},
    # ---------- Tier-2 精炼系 ----------
    {"id": "flux", "name": "流转", "tag": "转", "tier": 2, "cost": 50,
     "requires": ["refine"], "mutex_group": None,
     "desc": "消耗再 -1（最低 0）。"},
    {"id": "inspiration", "name": "灵感", "tag": "灵", "tier": 2, "cost": 50,
     "requires": ["refine"], "mutex_group": None,
     "desc": "额外抽 1 张牌；没有抽牌效果的牌改为攻击伤害 +2。"},
    # ---------- Tier-3 终式（须先点亮对应 Tier-2） ----------
    {"id": "annihilator", "name": "歼灭", "tag": "灭", "tier": 3, "cost": 75,
     "requires": ["edge"], "mutex_group": None,
     "desc": "所有攻击伤害再 +5；无攻击效果的牌改为格挡再 +5。"},
    {"id": "fortify", "name": "金城", "tag": "城", "tier": 3, "cost": 75,
     "requires": ["bulwark"], "mutex_group": None,
     "desc": "所有格挡再 +6；没有格挡效果的牌改为获得 6 点格挡。"},
    {"id": "transcendent", "name": "超凡", "tag": "凡", "tier": 3, "cost": 75,
     "requires": ["overload"], "mutex_group": None,
     "desc": "非攻击数值再 +3；若没有此类效果，攻击伤害 +4。"},
    {"id": "momentum", "name": "乘势", "tag": "势", "tier": 3, "cost": 75,
     "requires": ["resonance"], "mutex_group": None,
     "desc": "本回合第一张攻击牌的首击伤害再 +6；该牌不是攻击牌时此成长不生效。"},
    {"id": "frugality", "name": "俭用", "tag": "俭", "tier": 3, "cost": 75,
     "requires": ["flux"], "mutex_group": None,
     "desc": "若此牌消耗为 0，打出时额外获得 1 点能量；否则消耗再 -1（最低 0）。"},
    {"id": "insight", "name": "洞见", "tag": "见", "tier": 3, "cost": 75,
     "requires": ["inspiration"], "mutex_group": None,
     "desc": "抽牌数再 +2；没有抽牌效果的牌改为攻击伤害 +3。"},

    # ---------- 迁移专用节点（仅旧档 forges 迁移产生，不可在锻造台选择） ----------
    {"id": "~sharpen", "name": "锋锐（旧）", "tag": "锋", "tier": 0, "cost": 25,
     "requires": [], "mutex_group": None, "legacy": True,
     "desc": "旧版锻造记录迁移节点，等价于一次锋锐。"},
    {"id": "~empower", "name": "强效（旧）", "tag": "强", "tier": 0, "cost": 25,
     "requires": [], "mutex_group": None, "legacy": True,
     "desc": "旧版锻造记录迁移节点，等价于一次强效。"},
    {"id": "~refine", "name": "精炼（旧）", "tag": "炼", "tier": 0, "cost": 25,
     "requires": [], "mutex_group": None, "legacy": True,
     "desc": "旧版锻造记录迁移节点，等价于一次精炼。"},
]
NODE_BY_ID = {n["id"]: n for n in FORGE_NODES}
# 可在锻造台选择的节点（迁移专用节点除外）
SELECTABLE_IDS = {n["id"] for n in FORGE_NODES if not n.get("legacy")}
# 旧版扁平分支 -> 逐次迁移节点（第 k 次重复选第 k 个）
LEGACY_BRANCH_MAP = {
    "sharpen": ["sharpen", "edge", "annihilator", "~sharpen"],
    "empower": ["empower", "overload", "transcendent", "~empower"],
    "refine": ["refine", "flux", "frugality", "~refine"],
}

# empower/overload/transcendent 作用的“非攻击数值”效果类型
_EMPOWER_TYPES = ("apply_status", "set_status", "draw", "heal", "gain_energy")


def public_tree():
    """成长树只读定义（供锻造台渲染：节点/前置/互斥/价格）。"""
    return {
        "nodes": [dict(n) for n in FORGE_NODES if not n.get("legacy")],
        "mutex_groups": [{"id": gid, "desc": desc} for gid, desc in MUTEX_GROUPS.items()],
    }


def public_branches():
    """兼容旧客户端：仍返回 Tier-1 三个主干分支。"""
    return [dict(NODE_BY_ID[bid]) for bid in ("sharpen", "empower", "refine")]


def node_name(nid):
    n = NODE_BY_ID.get(nid)
    return n["name"] if n else nid


# 旧名兼容：service 层历史代码按 branch_name 取名
def branch_name(bid):
    return node_name(bid)


def node_cost(nid):
    n = NODE_BY_ID.get(nid)
    return n["cost"] if n else FORGE_COST


def migrate_legacy_forges(legacy_forges):
    """把旧版扁平 forges:[分支…] 映射为新版成长节点列表（保持选择先后序）。

    每个分支的前 3 次分别映射到该系 Tier-1/Tier-2/Tier-3 的等价节点，
    第 4 次及以上映射到 "~" 迁移节点（逐值复刻旧规则的无限叠加）。
    混选分支（如 sharpen+empower）各自独立映射，不触发互斥。
    """
    seen = {}
    out = []
    for bid in legacy_forges or ():
        seq = seen.get(bid, 0)
        table = LEGACY_BRANCH_MAP.get(bid)
        if table is None:
            continue
        out.append(table[min(seq, len(table) - 1)])
        seen[bid] = seq + 1
    return out


def available_nodes(growth):
    """给定实例已解锁节点，返回当前可解锁的节点 id 集合（前置满足 + 互斥未占 + 未点亮）。"""
    have = set(growth or ())
    used_groups = {NODE_BY_ID[n]["mutex_group"]
                   for n in have if n in NODE_BY_ID and NODE_BY_ID[n].get("mutex_group")}
    avail = set()
    for n in FORGE_NODES:
        if n.get("legacy") or n["id"] in have:
            continue
        if n.get("mutex_group") and n["mutex_group"] in used_groups:
            continue
        if any(req not in have for req in n.get("requires", [])):
            continue
        avail.add(n["id"])
    return avail


def validate_unlock(growth, node_id):
    """校验某实例能否解锁 node_id；不合法返回原因字符串，合法返回 None。"""
    n = NODE_BY_ID.get(node_id)
    if n is None or n.get("legacy"):
        return "unknown growth node"
    have = set(growth or ())
    if node_id in have:
        return "growth node already unlocked"
    missing = [req for req in n.get("requires", []) if req not in have]
    if missing:
        return f"requires node: {','.join(missing)}"
    gid = n.get("mutex_group")
    if gid:
        blocked = next((x for x in have
                        if x in NODE_BY_ID and NODE_BY_ID[x].get("mutex_group") == gid), None)
        if blocked:
            return f"mutex group '{gid}' already has '{blocked}'"
    return None


def _has_type(effects, t):
    return any(e.get("type") == t for e in effects)


def effective_card(base_card, growth):
    """把基础卡牌定义按实例已解锁成长节点换算成生效卡牌（深拷贝，不污染注册表）。

    growth 为节点 id 列表（新档）；旧调用方传入扁平 forges 也兼容（按迁移映射换算）。
    节点按解锁先后序应用——成长只做加法/降费，顺序对最终数值无影响。
    """
    nodes = list(growth or ())
    if any(n not in NODE_BY_ID for n in nodes):
        # 历史调用形态：纯旧分支 id 列表（仅测试/遗留路径会走到）
        nodes = migrate_legacy_forges(nodes)

    card = dict(base_card)
    effects = [dict(e) for e in card.get("effects", [])]

    def damage_effects():
        return [e for e in effects if e.get("type") == "damage"]

    def block_effects():
        return [e for e in effects if e.get("type") == "gain_block"]

    def add_dmg(amount):
        for e in damage_effects():
            e["value"] = e.get("value", 0) + amount

    def add_block(amount):
        for e in block_effects():
            e["value"] = e.get("value", 0) + amount

    def add_gain_block(amount):
        """没有格挡效果时追加一个获得格挡效果（作用于玩家）。"""
        effects.append({"type": "gain_block", "value": amount, "target": "player"})

    def empower_value(amount, fallback_dmg):
        targets = [e for e in effects if e.get("type") in _EMPOWER_TYPES]
        if targets:
            for e in targets:
                e["value"] = e.get("value", 0) + amount
        else:
            add_dmg(fallback_dmg)

    first_attack_bonus = 0   # 共鸣/乘势：本回合第一张攻击牌的额外伤害（运行时按牌生效）
    energy_on_zero = 0       # 俭用：费用归零时额外获得能量

    for nid in nodes:
        if nid in ("sharpen", "~sharpen"):
            if damage_effects():
                add_dmg(3)
            elif block_effects():
                add_block(3)
            else:
                add_gain_block(3)
        elif nid in ("edge",):
            if damage_effects():
                add_dmg(3)
            elif block_effects():
                add_block(3)
            else:
                add_gain_block(3)
        elif nid == "annihilator":
            if damage_effects():
                add_dmg(5)
            elif block_effects():
                add_block(5)
            else:
                add_gain_block(5)
        elif nid == "bulwark":
            if block_effects():
                add_block(5)
            else:
                add_gain_block(5)
        elif nid == "fortify":
            if block_effects():
                add_block(6)
            else:
                add_gain_block(6)
        elif nid in ("empower", "~empower"):
            empower_value(1, 2)
        elif nid == "overload":
            empower_value(2, 3)
        elif nid == "transcendent":
            empower_value(3, 4)
        elif nid == "resonance":
            if damage_effects():
                first_attack_bonus += 4
        elif nid == "momentum":
            if damage_effects():
                first_attack_bonus += 6
        elif nid in ("refine", "~refine"):
            card["cost"] = max(0, card.get("cost", 0) - 1)
        elif nid == "flux":
            card["cost"] = max(0, card.get("cost", 0) - 1)
        elif nid == "frugality":
            if card.get("cost", 0) == 0:
                energy_on_zero += 1
            else:
                card["cost"] = max(0, card.get("cost", 0) - 1)
        elif nid == "inspiration":
            if _has_type(effects, "draw"):
                for e in effects:
                    if e.get("type") == "draw":
                        e["value"] = e.get("value", 0) + 1
            else:
                add_dmg(2)
        elif nid == "insight":
            if _has_type(effects, "draw"):
                for e in effects:
                    if e.get("type") == "draw":
                        e["value"] = e.get("value", 0) + 2
            else:
                add_dmg(3)

    if energy_on_zero:
        effects.append({"type": "gain_energy", "value": energy_on_zero, "target": "player"})
    # 共鸣 + 乘势：仅作用于“本回合打出的第一张攻击牌”，引擎按 attacks_played 判定；
    # 写进卡牌定义的扩展字段，由 Battle.play_card 折算进首个伤害效果。
    # （仅对攻击牌设置：resonance/momentum 对非攻击牌不产生 first_attack_bonus 键）
    if first_attack_bonus:
        card["first_attack_bonus"] = first_attack_bonus
    card["effects"] = effects
    return card
