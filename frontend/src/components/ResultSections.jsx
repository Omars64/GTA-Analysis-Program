export default function ResultSections({ sections = {} }) {
  const entries = Object.entries(sections)
  if (!entries.length) return null
  return <div className="section-grid">
    {entries.map(([category, items]) => (
      <section className="result-section glass-panel" key={category}>
        <div className="section-title"><h3>{category}</h3><span>{items.length}</span></div>
        <div className="section-list">
          {items.map((row, i) => <div className="section-row" key={`${row.item}-${i}`}>
            <div><strong>{row.item || 'Untitled item'}</strong>{row.details && <p>{row.details}</p>}</div>
            <div className="row-proof" title={`${row.source_count || 1} source(s)`}>{row.verified ? 'VERIFIED' : `${Math.round((row.confidence || 0) * 100)}%`}</div>
          </div>)}
        </div>
      </section>
    ))}
  </div>
}
