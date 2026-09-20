import React from 'react'
import { useStore } from '../store'
import { growthTagList } from '../growth'

function GrowthTags({ growth }) {
  if (!growth || growth.length === 0) return null
  return <em className="ftags">{growthTagList(growth)}</em>
}

export default function DeckView({ mode }) {
  const { view, cards, cardMeta } = useStore()
  const deck = view ? view.deck : null
  if (mode === 'extras') {
    // 主页展示全部卡牌
    return (
      <div className="panellist">
        <h3>卡牌图鉴（{cards.length}）</h3>
        <div className="decklist">
          {cards.map((c) => (
            <div key={c.id} className={`deckcard ${c.tier}`}>
              <span className="cname">{c.name}</span>
              <span className="cdesc">{c.desc}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }
  if (!deck) return null

  // deck 项：新档为 {uid,id,growth,growth_cost}
  const groups = {}
  const order = []
  deck.forEach((item) => {
    const id = typeof item === 'string' ? item : item.id
    if (!groups[id]) {
      groups[id] = { id, count: 0, growths: [], invested: 0 }
      order.push(id)
    }
    groups[id].count += 1
    if (typeof item !== 'string') {
      groups[id].growths.push(item.growth || [])
      groups[id].invested += item.growth_cost || 0
    }
  })

  return (
    <div className="panellist">
      <h3>牌组（{deck.length}）</h3>
      <div className="decklist">
        {order.map((id) => {
          const g = groups[id]
          const c = cardMeta(id) || { id, name: id, desc: '', tier: '' }
          // 同名卡的成长分布：各实例独立显示（如 ×4 中 锋 / 锋刃）
          const marks = g.growths.map((gr, i) => <GrowthTags key={i} growth={gr} />)
          return (
            <div key={id} className={`deckcard ${c.tier}`}>
              <span className="cname">
                {c.name} <em>×{g.count}</em>{' '}
                {marks.some((m) => m) && <span className="fmarks">{marks}</span>}
                {g.invested > 0 && <i className="invested">累计投入 {g.invested}</i>}
              </span>
              <span className="cdesc">{cardBadge(c)} · {c.desc}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function cardBadge(card) {
  switch (card.type) {
    case 'attack': return '攻击'
    case 'skill': return '技能'
    case 'power': return '能力'
    default: return ''
  }
}
