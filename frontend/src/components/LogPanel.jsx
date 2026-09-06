export default function LogPanel({ logs = [] }) {
  return (
    <div className="terminal">
      <div className="terminal-bar"><span>LIVE RUN CONSOLE</span><span>{logs.length} events</span></div>
      <div className="terminal-body">
        {logs.length === 0 && <div className="log-line muted">&gt; Waiting for intelligence scan…</div>}
        {logs.map((log, i) => (
          <div className={`log-line ${log.level || 'info'}`} key={`${log.seq || i}-${i}`}>
            <span className="log-time">{log.at ? new Date(log.at).toLocaleTimeString() : '--:--:--'}</span>
            <span>&gt; {log.message || String(log)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
