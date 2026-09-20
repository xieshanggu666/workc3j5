import React from 'react'

// 成长树节点展示元信息（标签字与中文名）。服务端 /api/runs 视口下发 forge_tree，
// 这里的表仅用于在服务端元数据缺失（旧缓存/异常）时兜底渲染。
export const GROWTH_TAGS = {
  sharpen: { tag: '锋', name: '锋锐' },
  empower: { tag: '强', name: '强效' },
  refine: { tag: '炼', name: '精炼' },
  edge: { tag: '刃', name: '开刃' },
  bulwark: { tag: '壁', name: '坚壁' },
  overload: { tag: '载', name: '过载' },
  resonance: { tag: '鸣', name: '共鸣' },
  flux: { tag: '转', name: '流转' },
  inspiration: { tag: '灵', name: '灵感' },
  annihilator: { tag: '灭', name: '歼灭' },
  fortify: { tag: '城', name: '金城' },
  transcendent: { tag: '凡', name: '超凡' },
  momentum: { tag: '势', name: '乘势' },
  frugality: { tag: '俭', name: '俭用' },
  insight: { tag: '见', name: '洞见' },
}

export function growthTagOf(nodeId) {
  return GROWTH_TAGS[nodeId]?.tag || nodeId?.slice(0, 1) || '?'
}

export function growthNameOf(nodeId) {
  return GROWTH_TAGS[nodeId]?.name || nodeId
}

// 已点亮成长节点 -> 一串小角标（按解锁顺序）
export function growthTagList(growth) {
  if (!growth || growth.length === 0) return null
  return (
    <>
      {growth.map((g, i) => (
        <i key={`${g}-${i}`} className={`ftag ${g}`} title={growthNameOf(g)}>
          {growthTagOf(g)}
        </i>
      ))}
    </>
  )
}
