export default function ProgressBar({ value, status }) {
  const pct = Math.min(100, Math.max(0, value || 0))
  return (
    <div style={{ marginTop: '0.75rem' }}>
      <div
        style={{
          width: '100%',
          height: 10,
          borderRadius: 999,
          background: 'rgba(15,23,42,0.9)',
          overflow: 'hidden',
          boxShadow: 'inset 0 0 0 1px rgba(15,23,42,0.8)',
        }}
      >
        <div
          style={{
            width: pct + '%',
            height: '100%',
            borderRadius: 999,
            background: 'linear-gradient(90deg, #22c55e, #a3e635, #38bdf8)',
            transition: 'width 0.2s ease-out',
          }}
        />
      </div>
      {status && (
        <div style={{ marginTop: 4, fontSize: 12, color: '#9ca3af', display: 'flex', justifyContent: 'space-between' }}>
          <span>{status}</span>
          <span>{Math.round(pct)}%</span>
        </div>
      )}
    </div>
  )
}