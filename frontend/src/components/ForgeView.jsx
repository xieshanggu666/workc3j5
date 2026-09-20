import React, { useMemo, useState } from 'react'
import { api, handleActError } from '../api'
import { useStore } from '../store'
import { GROWTH_TAGS, growthTagList } from '../growth'

// 锻造节点：花金币为一张指定卡牌实例点亮成长树节点（每节点限一次）。
// 成长节点带前置（requires）与互斥（mutex_group）：未满足前置/被互斥的节点禁用；
// 选择与花费按实例保存在服务端，本组件只依据视口的 forge_tree/growth_options 渲染。
export default function ForgeView({ view }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [selected, setSelected] = useState(null) // 卡牌实例 uid
  const runId = useStore((s) => s.runId)
  const applyRun = useStore((s) => s.applyRun)
  const cardMeta = useStore((s) => s.cardMeta)

  const tree = view.forge_tree || { nodes: [], mutex_groups: [] }
  const nodeById = useMemo(
    () => Object.fromEntries((tree.nodes || []).map((n) => [n.id, n])),
    [tree],
  )
  const optionsByUid = view.growth_options || {}

  // 同名卡按实例列出，各自显示已点亮的成长节点与累计投入
  const instances = useMemo(
    () => (view.deck || []).map((d) => ({ ...d, meta: cardMeta(d.id) })),
    [view.deck, cardMeta],
  )

  const selectedInst = instances.find((i) => i.uid === selected) || null
  const available = new Set(selectedInst ? (optionsByUid[selectedInst.uid] || []) : [])
  const have = new Set(selectedInst ? (selectedInst.growth || []) : [])
  // 互斥说明（被选中卡当前占用的组）
  const mutexHint = useMemo(() => {
    if (!selectedInst) return ''
    const usedGroup = (selectedInst.growth || [])
      .map((g) => nodeById[g]?.mutex_group)
      .find(Boolean)
    const g = (tree.mutex_groups || []).find((m) => m.id === usedGroup)
    return g ? g.desc : ''
  }, [selectedInst, nodeById, tree.mutex_groups])

  async function unlock(nodeId) {
    if (!selected || busy) return
    setBusy(true); setErr('')
    try {
      const res = await api.act(runId, { action: 'forge', card: selected, node: nodeId })
      applyRun(res.run)
      // 成长后仍可查看该卡，但每节点只能成长一次：是否保留选中交给视口的可用性决定
    } catch (e) {
      setErr(await handleActError(e, runId, applyRun))
    } finally {
      setBusy(false)
    }
  }

  const forgeOpen = view.forge_available === true

  return (
    <div className="overlay">
      <div className="forgecard panel">
        <h2>🔨 锻造台 · 成长树</h2>
        <p className="forgedesc">
          选择一张卡牌，花费金币点亮成长节点。节点有前置与互斥：深层节点须先点亮上层，
          互斥分支只能二选一；同名卡各自独立成长，投入随实例永久保存并跨章继承。
        </p>
        <div className="forgelist">
          {instances.map((inst) => {
            const c = inst.meta || { name: inst.id, desc: '', tier: '' }
            const isSel = selected === inst.uid
            const invested = inst.growth_cost || 0
            return (
              <button
                key={inst.uid}
                className={`forgeinst ${c.tier} ${isSel ? 'sel' : ''}`}
                onClick={() => setSelected(inst.uid)}
                disabled={busy}
                title={c.desc}
              >
                <span className="cname">
                  {c.name}
                  {(inst.growth || []).length > 0 && (
                    <em className="ftags">{growthTagList(inst.growth)}</em>
                  )}
                  {invested > 0 && <i className="invested">已投入 {invested}</i>}
                </span>
                <span className="cdesc">{c.desc}</span>
              </button>
            )
          })}
        </div>

        {selectedInst ? (
          <div className="growthtree">
            <div className="gt-head">
              <b>{(selectedInst.meta || {}).name || selectedInst.id}</b>
              <span className="gt-gold">
                已投入 {selectedInst.growth_cost || 0} ｜ 持有金币 {view.gold}
              </span>
            </div>
            {mutexHint && <div className="gt-mutex">🔒 {mutexHint}</div>}
            <div className="gt-grid">
              {(tree.nodes || []).map((n) => {
                const owned = have.has(n.id)
                const can = forgeOpen && available.has(n.id) && view.gold >= n.cost
                const reqMissing = (n.requires || []).some((r) => !have.has(r))
                const state = owned ? 'owned' : can ? 'available' : 'locked'
                return (
                  <button
                    key={n.id}
                    className={`gnode tier${n.tier} ${state}`}
                    disabled={!can || busy}
                    onClick={() => unlock(n.id)}
                    title={nodeHint(n, owned, reqMissing)}
                  >
                    <span className={`ftag big ${n.id}`}>{n.tag}</span>
                    <span className="gname">{n.name}</span>
                    <span className="gcost">{owned ? '已点亮' : `${n.cost} 金币`}</span>
                    <span className="gdesc">{n.desc}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ) : (
          <p className="forgedesc">请先在上方选择一张卡牌查看成长路线。</p>
        )}

        {!forgeOpen && <div className="info">本次锻造节点已使用，启程前往下一处节点。</div>}
        {err && <div className="error">{err}</div>}
      </div>
    </div>
  )
}

function nodeHint(n, owned, reqMissing) {
  if (owned) return `${n.name}：已点亮`
  const req = (n.requires || []).map((r) => GROWTH_TAGS[r]?.name || r).join('、')
  const parts = [n.desc]
  if (req) parts.push(reqMissing ? `需要先点亮：${req}` : `前置：${req}`)
  return parts.join('\n')
}
