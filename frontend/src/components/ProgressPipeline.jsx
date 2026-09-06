const stages = [
  ['discover', 'Discover'], ['collect', 'Collect'], ['extract', 'Extract'], ['normalize', 'Normalize'],
  ['verify', 'Verify'], ['enrich', 'Enrich'], ['export', 'Export'], ['complete', 'Complete'],
]

export default function ProgressPipeline({ progress = 0, stage = 'queued', message = 'Ready' }) {
  const activeIndex = Math.max(0, stages.findIndex(([key]) => key === stage))
  return (
    <div className="pipeline-wrap">
      <div className="progress-head"><span>{message}</span><strong>{Math.round(progress)}%</strong></div>
      <div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
      <div className="pipeline">
        {stages.map(([key, label], idx) => {
          const done = progress === 100 || idx < activeIndex
          const active = key === stage || (stage === 'initialize' && idx === 0)
          return <div className={`pipeline-step ${done ? 'done' : ''} ${active ? 'active' : ''}`} key={key}>
            <span className="pipeline-dot" />
            <small>{label}</small>
          </div>
        })}
      </div>
    </div>
  )
}
