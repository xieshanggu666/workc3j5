"""卡牌成长树：前置/互斥分支、按实例保存选择与成本、贯通战斗/商店移除/跨章/续局/回放、旧档迁移。"""
import pytest

from app import service, mapgen, db
from app.cards import get_card
from app.forging import (
    FORGE_COST, effective_card, validate_unlock, available_nodes,
    migrate_legacy_forges, node_cost,
)


# ---------- 纯函数：成长节点换算 ----------
def test_effective_card_tier1_growth():
    strike = get_card("strike")  # 6 伤 / 1 费
    eff = effective_card(strike, ["sharpen", "refine"])
    assert eff["effects"][0]["value"] == 9   # 6 + 3
    assert eff["cost"] == 0                  # 1 - 1，最低 0
    # 不污染注册表
    assert get_card("strike")["effects"][0]["value"] == 6
    assert get_card("strike")["cost"] == 1


def test_effective_card_empower_and_refine_floor():
    flex = get_card("flex")  # 获得 2 力量
    eff = effective_card(flex, ["empower"])
    assert eff["effects"][0]["value"] == 3
    guard = get_card("guard")  # 5 格挡：锋锐无攻击效果时转成格挡强化
    assert effective_card(guard, ["sharpen"])["effects"][0]["value"] == 8
    # 精炼不会把费用压成负数（refine 只降一次，旧版无限叠降由迁移节点复刻）
    zero = effective_card(get_card("adrenaline"), ["refine", "flux"])
    assert zero["cost"] == 0


# ---------- 纯函数：前置条件与互斥 ----------
def test_requires_must_be_unlocked_first():
    # edge 需要先 sharpen
    assert validate_unlock([], "edge") is not None
    assert validate_unlock(["sharpen"], "edge") is None
    # 终式需要对应 Tier-2
    assert validate_unlock(["sharpen", "edge"], "annihilator") is None
    assert validate_unlock(["sharpen", "bulwark"], "annihilator") is not None
    # 已点亮不可重复
    assert validate_unlock(["sharpen"], "sharpen") is not None
    # 跨系节点不互为前置（强效不挡精炼）
    assert validate_unlock(["empower"], "refine") is None


def test_edge_and_bulwark_are_mutex():
    # 开刃与坚壁互斥：选了其一，另一路（含终式）永久锁定
    assert validate_unlock(["sharpen", "edge"], "bulwark") is not None
    assert validate_unlock(["sharpen", "bulwark"], "edge") is not None
    assert validate_unlock(["sharpen", "bulwark"], "fortify") is None
    assert validate_unlock(["sharpen", "edge"], "fortify") is not None
    # 三系主干不互斥：锋锐 + 强效 + 精炼可以同时点亮
    assert validate_unlock(["sharpen", "empower"], "refine") is None
    avail = available_nodes(["sharpen"])
    assert {"edge", "bulwark", "empower", "refine"} <= avail
    assert "annihilator" not in avail  # 还差 edge
    avail_edge = available_nodes(["sharpen", "edge"])
    assert "bulwark" not in avail_edge and "annihilator" in avail_edge


def test_deep_growth_numbers_and_first_attack():
    # 歼灭：6 + 3(锋锐) + 3(开刃) + 5(歼灭) = 17
    eff = effective_card(get_card("strike"), ["sharpen", "edge", "annihilator"])
    assert eff["effects"][0]["value"] == 17
    # 坚壁系作用于格挡：guard 5 + 3(锋锐) + 5(坚壁) + 6(金城) = 19
    wall = effective_card(get_card("guard"), ["sharpen", "bulwark", "fortify"])
    assert wall["effects"][0]["value"] == 19
    # 坚壁给无格挡的攻击牌追加格挡效果
    wall_strike = effective_card(get_card("strike"), ["sharpen", "bulwark"])
    assert [e["type"] for e in wall_strike["effects"]] == ["damage", "gain_block"]
    # 共鸣/乘势写入首击加成（仅攻击牌）
    reso = effective_card(get_card("strike"), ["empower", "resonance"])
    assert reso.get("first_attack_bonus") == 4
    assert effective_card(get_card("guard"), ["empower", "resonance"]).get("first_attack_bonus") is None
    mom = effective_card(get_card("strike"), ["empower", "resonance", "momentum"])
    assert mom["first_attack_bonus"] == 10
    # frugality：0 费牌额外获得能量；非 0 费牌继续降费
    frugal0 = effective_card(get_card("adrenaline"), ["refine", "flux", "frugality"])
    assert frugal0["cost"] == 0
    assert any(e["type"] == "gain_energy" and e["value"] == 1 for e in frugal0["effects"])
    frugal1 = effective_card(get_card("strike"), ["refine", "flux", "frugality"])
    assert frugal1["cost"] == 0
    # 灵感/洞见：有抽牌的加抽牌数，没抽牌的转伤害
    tr = effective_card(get_card("pommel"), ["refine", "inspiration", "insight"])
    assert next(e for e in tr["effects"] if e["type"] == "draw")["value"] == 1 + 1 + 2
    ins_strike = effective_card(get_card("strike"), ["refine", "inspiration", "insight"])
    assert ins_strike["effects"][0]["value"] == 6 + 2 + 3


# ---------- 旧版扁平 forges 迁移 ----------
def test_migrate_legacy_forges_is_value_equivalent():
    # sharpen 重复 3 次 -> sharpen/edge/annihilator；伤害 6+3+3+5=17
    assert migrate_legacy_forges(["sharpen", "sharpen", "sharpen"]) == [
        "sharpen", "edge", "annihilator"]
    eff = effective_card(get_card("strike"), migrate_legacy_forges(
        ["sharpen", "sharpen", "sharpen"]))
    assert eff["effects"][0]["value"] == 17
    # 第 4 次起走迁移专用节点，逐值复刻旧规则（每次 +3）
    nodes4 = migrate_legacy_forges(["sharpen"] * 4)
    assert nodes4[-1] == "~sharpen"
    assert effective_card(get_card("strike"), nodes4)["effects"][0]["value"] == 20
    # 混选分支各自独立映射，不触发互斥
    mixed = migrate_legacy_forges(["sharpen", "empower"])
    assert mixed == ["sharpen", "empower"]
    # 旧 refine 两次 -> refine/flux（总降费 2）
    assert migrate_legacy_forges(["refine", "refine"]) == ["refine", "flux"]
    assert effective_card(get_card("strike"), ["refine", "flux"])["cost"] == 0


# ---------- 地图/节点 ----------
def _find_forge_path(seed_start=0):
    """返回 (seed, 到锻造节点的完整路径)，最多探两行。"""
    for seed in range(seed_start, seed_start + 500):
        m = mapgen.generate_map(seed)
        for n0 in m["routes"][m["start"]]:
            if m["nodes"][n0]["type"] == mapgen.FORGE:
                return seed, [n0]
            for n1 in m["routes"][n0]:
                if m["nodes"][n1]["type"] == mapgen.FORGE:
                    return seed, [n0, n1]
    raise AssertionError("no forge node")


def _find_enemy_path(seed_start=0):
    for seed in range(seed_start, seed_start + 200):
        m = mapgen.generate_map(seed)
        for n0 in m["routes"][m["start"]]:
            if m["nodes"][n0]["type"] in (mapgen.ENCOUNTER, mapgen.ELITE):
                return seed, [n0]
    raise AssertionError("no enemy node")


def _walk(client, rid, nodes):
    run = None
    for n in nodes:
        run = client.post(f"/api/runs/{rid}/act",
                          json={"action": "choose_node", "node": n}).json()["run"]
    return run


def _give_gold(rid, gold):
    rec = service.load_run(rid)
    rec["state"]["gold"] = gold
    db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])


def _earn_gold_via_logged_actions(client, rid, target, cap=100):
    """走合法行动（打遭遇战 + 领取金币奖励）攒到 target 金币——所有变化都进动作日志，
    回放逐位可复现（区别于直接改库的 _give_gold）。返回到达锻造节点前的当前视口。

    锻造等已发生的花费会抬高所需累计收入：target 是“还要再花的钱”，这里按
    当前余额判断，调用方只需保证成长节点上的金币足够即可。
    """
    for _ in range(cap):
        view = client.get(f"/api/runs/{rid}/resume").json()
        if view["gold"] >= target:
            return view
        if view["status"] != "in_progress":
            raise AssertionError(f"run ended with only {view['gold']} gold")
        if view["in_battle"]:
            hand = view["battle"]["hand"]
            energy = view["battle"]["energy"]
            playable = [h for h in hand if (h.get("cost", 1) if isinstance(h, dict) else 1) <= energy]
            if playable:
                h = playable[0]
                body = {"action": "play", "card": h["uid"] if isinstance(h, dict) else h}
            else:
                body = {"action": "end_turn"}
            assert client.post(f"/api/runs/{rid}/act", json=body).status_code == 200
            continue
        if not view["reward_claimed"] and view["reward_options"]:
            idx = next((i for i, o in enumerate(view["reward_options"])
                        if o.get("kind") == "gold"), 0)
            assert client.post(f"/api/runs/{rid}/act",
                               json={"action": "claim_reward", "option": idx}).status_code == 200
            continue
        # 优先遭遇（攒金币）；战斗之外的节点里奖励/休息次之，锻造最后（避免提前消耗配额）
        nxt = next((n for n in view["reachable"]
                    if n["type"] in (mapgen.ENCOUNTER, mapgen.ELITE)), None)
        if nxt is None:
            nxt = sorted(view["reachable"],
                         key=lambda n: {mapgen.REST: 0, mapgen.REWARD: 1,
                                        mapgen.SHOP: 2, mapgen.FORGE: 9}.get(n["type"], 5))[0]
        assert client.post(f"/api/runs/{rid}/act",
                           json={"action": "choose_node", "node": nxt["id"]}).status_code == 200
    raise AssertionError("could not earn enough gold")


def _forge_path_from_current(client, rid):
    """从当前存档位置找一个最近的可达锻造节点，返回行走路径。"""
    view = client.get(f"/api/runs/{rid}/resume").json()
    m = view["map"]

    def search(pos, depth):
        if depth > 4:
            return None
        for nid in m["routes"].get(pos, []):
            if m["nodes"][nid]["type"] == mapgen.FORGE:
                return [nid]
            sub = search(nid, depth + 1)
            if sub:
                return [nid] + sub
        return None

    path = search(view["position"], 0)
    if not path:
        raise AssertionError("no reachable forge node")
    return view["seed"], path


# ---------- 锻造节点：金币校验 + 防重复扣款 ----------
def test_forge_requires_gold_and_deducts_once(client):
    seed, path = _find_forge_path()
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    run = _walk(client, rid, path)
    assert run["forge_available"] is True
    assert run["forge_cost"] == FORGE_COST
    first_uid = run["deck"][0]["uid"]
    assert "sharpen" in run["growth_options"][first_uid]

    # 金币不足 -> 400，不产生任何效果
    poor = client.post(f"/api/runs/{rid}/act",
                       json={"action": "forge", "card": first_uid, "node": "sharpen"})
    assert poor.status_code == 400

    _give_gold(rid, node_cost("sharpen") * 2)
    ok = client.post(f"/api/runs/{rid}/act",
                     json={"action": "forge", "card": first_uid, "node": "sharpen"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["run"]["gold"] == node_cost("sharpen")
    forged = body["log"][-1]["forged"]
    assert forged["node"] == "sharpen" and forged["growth_cost"] == node_cost("sharpen")
    # 重复锻造同一节点 -> 409，金币不再被扣
    dup = client.post(f"/api/runs/{rid}/act",
                      json={"action": "forge", "card": first_uid, "node": "edge"})
    assert dup.status_code == 409
    assert client.get(f"/api/runs/{rid}").json()["gold"] == node_cost("sharpen")
    # 该实例只记录第一次的成长节点与花费
    deck = {c["uid"]: c for c in client.get(f"/api/runs/{rid}").json()["deck"]}
    assert deck[first_uid]["growth"] == ["sharpen"]
    assert deck[first_uid]["growth_cost"] == node_cost("sharpen")


def test_forge_rejects_bad_card_or_node(client):
    seed, path = _find_forge_path()
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    _walk(client, rid, path)
    _give_gold(rid, 500)
    bad_card = client.post(f"/api/runs/{rid}/act",
                           json={"action": "forge", "card": "nope", "node": "sharpen"})
    assert bad_card.status_code == 400
    uid = service.load_run(rid)["state"]["deck"][0]
    bad_node = client.post(f"/api/runs/{rid}/act",
                           json={"action": "forge", "card": uid, "node": "overlord"})
    assert bad_node.status_code == 400
    # 失败请求不扣款
    assert service.load_run(rid)["state"]["gold"] == 500


def test_forge_rejects_missing_prerequisite(client):
    seed, path = _find_forge_path()
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    _walk(client, rid, path)
    _give_gold(rid, 500)
    uid = service.load_run(rid)["state"]["deck"][0]
    # 直接点终式（缺整条前置链）-> 400，不扣款
    r = client.post(f"/api/runs/{rid}/act",
                    json={"action": "forge", "card": uid, "node": "annihilator"})
    assert r.status_code == 400
    st = service.load_run(rid)["state"]
    assert st["gold"] == 500 and st["card_instances"][uid]["growth"] == []
    # 互斥分支：未点 sharpen 时 edge/bulwark 同样非法
    r2 = client.post(f"/api/runs/{rid}/act",
                     json={"action": "forge", "card": uid, "node": "edge"})
    assert r2.status_code == 400


def test_forge_mutex_branch_locked_after_choice(client):
    """前置配额用节点控制；互斥由成长规则保证：选了开刃后坚壁一路被锁（API 400）。"""
    seed, path = _find_forge_path()
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    _give_gold(rid, 1000)
    uid = service.load_run(rid)["state"]["deck"][0]
    _walk(client, rid, path)
    # 第一个锻造节点：点亮 sharpen
    assert client.post(f"/api/runs/{rid}/act",
                       json={"action": "forge", "card": uid, "node": "sharpen"}
                       ).status_code == 200
    # 纯函数：互斥规则（开刃/坚壁二选一，选边锁终式）
    assert validate_unlock(["sharpen", "edge"], "bulwark") is not None
    assert validate_unlock(["sharpen", "bulwark"], "edge") is not None
    assert validate_unlock(["sharpen", "bulwark"], "fortify") is None

    # API 链路：用状态夹具连续放出三个锻造配额，sharpen->edge 后再试 bulwark 必须 400
    def reopen_forge():
        rec = service.load_run(rid)
        rec["state"]["forge_claimed"] = False
        db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])

    reopen_forge()
    assert client.post(f"/api/runs/{rid}/act",
                       json={"action": "forge", "card": uid, "node": "edge"}
                       ).status_code == 200
    reopen_forge()
    locked = client.post(f"/api/runs/{rid}/act",
                         json={"action": "forge", "card": uid, "node": "bulwark"})
    assert locked.status_code == 400
    # 失败零副作用：不扣款、不加点
    st = service.load_run(rid)["state"]
    assert st["card_instances"][uid]["growth"] == ["sharpen", "edge"]

    # 互斥组的另一路终式同样被锁，但本路终式前置（edge）满足时可选
    assert validate_unlock(st["card_instances"][uid]["growth"], "fortify") is not None
    reopen_forge()
    ok = client.post(f"/api/runs/{rid}/act",
                     json={"action": "forge", "card": uid, "node": "annihilator"})
    assert ok.status_code == 200
    assert service.load_run(rid)["state"]["card_instances"][uid]["growth"] == [
        "sharpen", "edge", "annihilator"]


# ---------- 同名卡独立成长 ----------
def test_same_name_cards_grow_independently(client):
    seed, path = _find_forge_path()
    created = client.post("/api/runs", json={"seed": seed}).json()
    rid = created["run_id"]
    strikes = [c for c in created["deck"] if c["id"] == "strike"]
    assert len(strikes) >= 2  # 初始牌组有 4 张打击，各持独立 uid
    _walk(client, rid, path)
    _give_gold(rid, 500)

    target, other = strikes[0]["uid"], strikes[1]["uid"]
    r = client.post(f"/api/runs/{rid}/act",
                    json={"action": "forge", "card": target, "node": "sharpen"})
    assert r.status_code == 200
    deck = {c["uid"]: c for c in r.json()["run"]["deck"]}
    assert deck[target]["growth"] == ["sharpen"]
    assert deck[target]["growth_cost"] == node_cost("sharpen")
    assert deck[other]["growth"] == []
    assert deck[other]["growth_cost"] == 0


# ---------- 贯通战斗结算 ----------
def test_forge_takes_effect_in_next_battle(client):
    seed, epath = _find_enemy_path(0)
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    # 在开战前直接给 c1（打击）写入成长：锋锐 + 精炼
    rec = service.load_run(rid)
    rec["state"]["card_instances"]["c1"]["growth"] = ["sharpen", "refine"]
    db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])

    run = _walk(client, rid, epath)
    assert run["in_battle"] is True
    # 把 c1 精确放进手牌（确定性，不依赖洗牌）并压残敌人
    rec = service.load_run(rid)
    b = rec["state"]["battle"]
    b["hand"] = ["c1"]
    b["draw_pile"] = [u for u in b["draw_pile"] if u != "c1"]
    b["discard"] = [u for u in b["discard"] if u != "c1"]
    b["energy"], b["max_energy"] = 3, 3
    b["entities"]["enemy"]["hp"] = 30
    db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])

    view = client.get(f"/api/runs/{rid}").json()
    hand = view["battle"]["hand"]
    assert hand[0]["uid"] == "c1" and hand[0]["cost"] == 0  # 精炼后 0 费
    res = client.post(f"/api/runs/{rid}/act", json={"action": "play", "card": "c1"})
    assert res.status_code == 200
    dmg = [e["value"] for e in res.json()["log"]
           if isinstance(e, dict) and e.get("action") == "damage"]
    assert dmg == [9]  # 6 基础 + 3 锋锐


def test_first_attack_growth_only_boots_first_attack(client):
    """共鸣 + 乘势：只加成本回合第一张攻击牌；第二张恢复原数值。"""
    from app.engine import Battle
    from app.cards import CARDS
    # 直接用引擎构造两张共鸣+乘势打击的对局状态
    seed, epath = _find_enemy_path(0)
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    rec = service.load_run(rid)
    for uid in ("c1", "c2"):
        rec["state"]["card_instances"][uid]["growth"] = [
            "empower", "resonance", "momentum"]
    db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])
    _walk(client, rid, epath)
    rec = service.load_run(rid)
    b = rec["state"]["battle"]
    b["hand"] = ["c1", "c2"]
    b["draw_pile"] = [u for u in b["draw_pile"] if u not in ("c1", "c2")]
    b["discard"] = [u for u in b["discard"] if u not in ("c1", "c2")]
    b["energy"], b["max_energy"] = 6, 6
    b["entities"]["enemy"]["hp"] = 999
    db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])

    r1 = client.post(f"/api/runs/{rid}/act", json={"action": "play", "card": "c1"}).json()
    d1 = [e["value"] for e in r1["log"] if isinstance(e, dict) and e.get("action") == "damage"]
    # empower(+2) + resonance(+4) + momentum(+6) = 6+12 = 18
    assert d1 == [18]
    r2 = client.post(f"/api/runs/{rid}/act", json={"action": "play", "card": "c2"}).json()
    d2 = [e["value"] for e in r2["log"] if isinstance(e, dict) and e.get("action") == "damage"]
    # 第二张只有 empower：6 + 2 = 8
    assert d2 == [8]
    # 结束回合后下一回合首击再次生效
    client.post(f"/api/runs/{rid}/act", json={"action": "end_turn"})
    rec = service.load_run(rid)
    b = rec["state"]["battle"]
    c3 = next(u for u in b["hand"] if rec["state"]["card_instances"][u]["id"] == "strike")
    b["energy"], b["max_energy"] = 6, 6
    db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])
    r3 = client.post(f"/api/runs/{rid}/act", json={"action": "play", "card": c3}).json()
    d3 = [e["value"] for e in r3["log"] if isinstance(e, dict) and e.get("action") == "damage"]
    assert d3 == [18]


# ---------- 贯通续局 ----------
def test_forge_persists_across_resume(client):
    seed, path = _find_forge_path()
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    run = _walk(client, rid, path)
    uid = run["deck"][0]["uid"]
    _give_gold(rid, 500)
    client.post(f"/api/runs/{rid}/act",
                json={"action": "forge", "card": uid, "node": "empower"})
    resumed = client.get(f"/api/runs/{rid}/resume").json()
    by_uid = {c["uid"]: c for c in resumed["deck"]}
    assert by_uid[uid]["growth"] == ["empower"]
    assert by_uid[uid]["growth_cost"] == node_cost("empower")
    assert resumed["forge_available"] is False


# ---------- 贯通回放 ----------
def _new_run_seeded_to_forge_after_battles(client, need_gold, attempts=400):
    """尝试多颗种子：找一颗能合法攒够金币并走到（下一个）锻造节点的局。

    全程只走 API 行动，故动作日志完整、回放可逐位复现。返回 (rid, view)。
    """
    for seed in range(attempts):
        rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
        try:
            _earn_gold_via_logged_actions(client, rid, need_gold, cap=80)
            _, path = _forge_path_from_current(client, rid)
        except AssertionError:
            continue
        view = _walk(client, rid, path)
        if view["forge_available"] and view["gold"] >= need_gold:
            return rid, view
    raise AssertionError("no seed yields a reachable forge with enough gold")


def test_forge_recorded_in_replay(client):
    rid, run = _new_run_seeded_to_forge_after_battles(client, FORGE_COST)
    uid = run["deck"][0]["uid"]
    r = client.post(f"/api/runs/{rid}/act",
                    json={"action": "forge", "card": uid, "node": "refine"})
    assert r.status_code == 200
    replay = client.get(f"/api/runs/{rid}/replay").json()
    forged = [a for a in replay["actions"] if a["action"] == "forge"]
    assert len(forged) == 1
    payload = forged[0]["payload"]
    # 地图节点与成长节点分列：choose_node 用 map node，forge 载荷里 map node 为 None，
    # 成长节点 id 同时写在 node 与 branch（旧客户端兼容）
    assert payload["card"] == uid
    assert payload["node"] == "refine" and payload["branch"] == "refine"
    # 新版规则下逐位校验通过（成长树规则与录制一致，金币也来自日志内的战斗/奖励）
    assert replay["verification"]["mismatch"] == 0
    assert replay["verification"]["error"] == 0
    step = next(s for s in replay["steps"] if s["action"] == "forge")
    assert step["title"].endswith("精炼")
    assert "花费 25" in step["summary"]


def _growth_run_bot(client, rid, want_nodes, cap=200, target_uid=None):
    """合法行动机器人：遇战打牌（优先打击）、奖励优先金币，攒够当前成长节点的
    钱后优先走锻造节点并解锁 want_nodes 指定的成长链（默认点在同一张卡上）。
    所有动作都走 API（进日志）。章节结束（won/lost）即返回最终视口；
    只有在仍在进行中且超过 cap 未走完时才抛错。
    """
    remaining = list(want_nodes)
    forged = 0
    for _ in range(cap):
        view = client.get(f"/api/runs/{rid}/resume").json()
        if view["status"] != "in_progress":
            return view
        if view["in_battle"]:
            hand = view["battle"]["hand"]
            energy = view["battle"]["energy"]
            playable = [h for h in hand
                        if (h.get("cost", 1) if isinstance(h, dict) else 1) <= energy]
            if playable:
                pick = next((h for h in playable
                             if (h.get("id") if isinstance(h, dict) else h) == "strike"),
                            playable[0])
                body = {"action": "play",
                        "card": pick["uid"] if isinstance(pick, dict) else pick}
            else:
                body = {"action": "end_turn"}
            assert client.post(f"/api/runs/{rid}/act", json=body).status_code == 200
            continue
        if not view["reward_claimed"] and view["reward_options"]:
            idx = next((i for i, o in enumerate(view["reward_options"])
                        if o.get("kind") == "gold"), 0)
            assert client.post(f"/api/runs/{rid}/act",
                               json={"action": "claim_reward", "option": idx}).status_code == 200
            continue
        if view["forge_available"] and remaining:
            node_id = remaining[0]
            opts = view["growth_options"]
            # 优先往指定实例（跨章同一张卡）上点；否则任选一个当前可解锁的实例
            candidates = [target_uid] if target_uid else []
            candidates += [u for u in opts if u != target_uid]
            uid = next((u for u in candidates if u and node_id in opts.get(u, [])
                        and view["gold"] >= node_cost(node_id)), None)
            if uid is not None:
                r = client.post(f"/api/runs/{rid}/act",
                                json={"action": "forge", "card": uid, "node": node_id})
                assert r.status_code == 200, (node_id, r.text)
                remaining.pop(0)
                forged += 1
                target_uid = uid
                if not remaining:
                    return view
                continue
        reach = view["reachable"]
        if not reach:
            return view
        # 路由偏好：下一个节点钱够且指定卡可解锁时优先锻造；否则遭遇（攒钱）> 奖励 > 休息 > 锻造
        def rank(n):
            if n["type"] == mapgen.FORGE:
                ready = remaining and view["gold"] >= node_cost(remaining[0])
                return 0 if ready else 8
            return {mapgen.ENCOUNTER: 1, mapgen.ELITE: 1, mapgen.REWARD: 2,
                    mapgen.REST: 3, mapgen.SHOP: 4}.get(n["type"], 5)
        nxt = sorted(reach, key=rank)[0]
        assert client.post(f"/api/runs/{rid}/act",
                           json={"action": "choose_node", "node": nxt["id"]}).status_code == 200
    raise AssertionError(f"only completed {forged} forges within cap")


def test_forge_prerequisite_chain_replays_identically(client):
    """跨真实锻造节点点亮 sharpen->edge->annihilator（前置链），逐位回放一致。

    单章地图只有 4 行节点，难以凑齐 3 个锻造节点 + 150 金币，因此用 3 章远征：
    成长按卡牌实例跨章继承（也顺带覆盖跨章交接），在多章内走完整条前置链。
    """
    # seed 8 的机器人可在前两章走完整条链（第 3 章无需推进）
    exp_id = client.post("/api/expeditions",
                         json={"chapters": 3, "seed": 8}).json()["expedition"]["id"]
    rid = client.get(f"/api/expeditions/{exp_id}").json()["run"]["run_id"]
    chain = ["sharpen", "edge", "annihilator"]
    target_uid = None
    done = []
    chapter = 1
    while len(done) < len(chain) and chapter <= 3:
        _growth_run_bot(client, rid, [n for n in chain if n not in done],
                        cap=240, target_uid=target_uid)
        view = client.get(f"/api/runs/{rid}/resume").json()
        inst = {c["uid"]: c for c in view["deck"]}
        if target_uid is None:
            target_uid = next((u for u, c in inst.items() if c["growth"]), None)
        if target_uid in inst:
            done = inst[target_uid]["growth"]
        if len(done) == len(chain):
            break
        # 本章未走完整条链：章节须已通关才能推进；若机器人没能打赢本章则换种子失败
        assert view["status"] == "won", f"第 {chapter} 章未通关（done={done}）"
        adv = client.post(f"/api/expeditions/{exp_id}/advance", json={})
        assert adv.status_code == 200, adv.text
        rid = adv.json()["run"]["run_id"]
        chapter += 1
        # 跨章继承：成长节点与累计花费随交接快照带到新章
        carried = next(c for c in client.get(f"/api/runs/{rid}").json()["deck"]
                       if c["uid"] == target_uid)
        assert carried["growth"] == done
        assert carried["growth_cost"] == sum(node_cost(n) for n in done)
    assert done == chain, f"成长链未走完：{done}"

    # 整程回放：每章校验点逐位通过
    full = client.get(f"/api/expeditions/{exp_id}/replay").json()
    for ch in full["chapters"]:
        v = ch["replay"]["verification"]
        assert v["mismatch"] == 0 and v["error"] == 0, (ch["chapter"], v)
    # 在线最终章牌组与最后一章回放终态一致
    last = full["chapters"][-1]["replay"]
    grown = {c["uid"]: c for c in last["final_view"]["deck"]
             if c["growth"] == chain}
    assert target_uid in grown
    item = grown[target_uid]
    assert item["growth_cost"] == 25 + 50 + 75


# ---------- 奖励入牌：新实例独立成长 ----------
def test_battle_reward_add_card_creates_independent_instance(client):
    seed, epath = _find_enemy_path(0)
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    _walk(client, rid, epath)
    rec = service.load_run(rid)
    enemy_id = rec["state"]["battle"]["enemy"]
    # 压残敌人 + 手里塞打击，一击获胜
    b = rec["state"]["battle"]
    b["entities"]["enemy"]["hp"] = 1
    b["hand"] = ["c1"]
    b["energy"] = 3
    db.save_run(rid, rec["state"]["status"], rec["state"]["position"], rec["state"])
    res = client.post(f"/api/runs/{rid}/act", json={"action": "play", "card": "c1"})
    assert res.json()["run"]["status"] == "in_progress"
    opts = res.json()["run"]["reward_options"]
    card_idx = next(i for i, o in enumerate(opts) if o["kind"] == "card")
    expected_cid = next(e["card"] for e in opts[card_idx]["effects"] if e["type"] == "add_card")
    claimed = client.post(f"/api/runs/{rid}/act",
                          json={"action": "claim_reward", "option": card_idx})
    assert claimed.status_code == 200
    state = service.load_run(rid)["state"]
    new_uid = state["deck"][-1]
    assert state["card_instances"][new_uid] == {
        "id": expected_cid, "growth": [], "growth_cost": 0}
    # 新卡确实来自敌人掉落表，且 uid 不与旧实例撞号
    from app.enemies import get_enemy
    assert expected_cid in get_enemy(enemy_id)["reward_cards"]
    assert state["next_card_seq"] == len(state["card_instances"]) + 1
    # 新实例与同名旧卡（若有）成长状态互相独立
    same_name = [u for u, i in state["card_instances"].items() if i["id"] == expected_cid]
    assert new_uid in same_name
    assert all(state["card_instances"][u]["growth"] == [] for u in same_name)


# ---------- 旧档兼容 ----------
def test_legacy_save_migrates_mid_battle_and_plays(client):
    seed, epath = _find_enemy_path(0)
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    _walk(client, rid, epath)
    # 把存档退回旧版本形态：裸 id 牌堆/牌组，无实例表
    rec = db.load_run(rid)
    st = rec["state"]
    for pile in ("draw_pile", "hand", "discard"):
        st["battle"][pile] = [st["card_instances"][u]["id"] for u in st["battle"][pile]]
    st["battle"].pop("card_instances", None)
    st["deck"] = [inst["id"] for inst in st["card_instances"].values()]
    del st["card_instances"]
    del st["next_card_seq"]
    st.pop("forge_claimed", None)
    db.save_run(rid, st["status"], st["position"], st)

    resumed = client.get(f"/api/runs/{rid}/resume").json()
    # 牌组与手牌都迁移为实例结构（含成长树字段）
    assert all(isinstance(c, dict) and c["uid"] for c in resumed["deck"])
    assert all("growth" in c and "growth_cost" in c for c in resumed["deck"])
    assert all(isinstance(h, dict) and h["uid"] for h in resumed["battle"]["hand"])
    # 同名卡获得不同 uid，且战斗三堆合计仍是整副牌
    st2 = service.load_run(rid)["state"]
    piles = st2["battle"]["draw_pile"] + st2["battle"]["hand"] + st2["battle"]["discard"]
    assert sorted(piles) == sorted(st2["deck"])
    assert all(u in st2["card_instances"] for u in piles)
    assert all("forges" not in i for i in st2["card_instances"].values())
    # 续局后可正常打牌
    uid = resumed["battle"]["hand"][0]["uid"]
    play = client.post(f"/api/runs/{rid}/act", json={"action": "play", "card": uid})
    assert play.status_code == 200


def test_legacy_save_outside_battle_migrates(client):
    # 旧档停在奖励节点（无战斗结构）也能迁移
    rid = client.post("/api/runs", json={"seed": 1}).json()["run_id"]
    rec = db.load_run(rid)
    st = rec["state"]
    st["deck"] = [inst["id"] for inst in st["card_instances"].values()]
    del st["card_instances"]
    del st["next_card_seq"]
    db.save_run(rid, st["status"], st["position"], st)
    resumed = client.get(f"/api/runs/{rid}/resume").json()
    assert len(resumed["deck"]) == 7
    assert len({c["uid"] for c in resumed["deck"]}) == 7
    assert all(c["growth"] == [] and c["growth_cost"] == 0 for c in resumed["deck"])
    assert resumed["forge_claimed"] is True


def test_legacy_forges_records_migrate_to_growth(client):
    """带旧版扁平 forges（含叠加/混选）的存档迁移为成长节点且数值等价。"""
    seed, epath = _find_enemy_path(0)
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    _walk(client, rid, epath)
    rec = db.load_run(rid)
    st = rec["state"]
    # c1 打击：旧规则 sharpen x2 + refine（6+6 伤、0 费）
    st["card_instances"]["c1"]["forges"] = ["sharpen", "sharpen", "refine"]
    db.save_run(rid, st["status"], st["position"], st)

    client.get(f"/api/runs/{rid}/resume")
    st = service.load_run(rid)["state"]
    inst = st["card_instances"]["c1"]
    assert inst["growth"] == ["sharpen", "edge", "refine"]
    # 迁移成本按节点价回填：25 + 50 + 25
    assert inst["growth_cost"] == 100
    eff = effective_card(get_card("strike"), inst["growth"])
    assert eff["effects"][0]["value"] == 12 and eff["cost"] == 0
    # 战斗内实例表副本也迁移为新结构
    assert "forges" not in st["battle"]["card_instances"]["c1"]
    assert st["battle"]["card_instances"]["c1"]["growth"] == ["sharpen", "edge", "refine"]


# ---------- 旧客户端兼容：branch 字段仍可解锁 Tier-1 ----------
def test_legacy_branch_payload_still_works(client):
    seed, path = _find_forge_path()
    rid = client.post("/api/runs", json={"seed": seed}).json()["run_id"]
    run = _walk(client, rid, path)
    uid = run["deck"][0]["uid"]
    _give_gold(rid, 100)
    r = client.post(f"/api/runs/{rid}/act",
                    json={"action": "forge", "card": uid, "branch": "sharpen"})
    assert r.status_code == 200
    assert service.load_run(rid)["state"]["card_instances"][uid]["growth"] == ["sharpen"]
