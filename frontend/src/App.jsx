import { useEffect, useMemo, useState } from 'react'
import { Activity, Bell, Cloud, ShieldAlert, Zap } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const API = 'http://localhost:8000'
const WS = 'ws://localhost:8000/ws'

function severityClass(s) {
  return s === 'CRITICAL' ? 'critical' : s === 'HIGH' ? 'high' : s === 'MEDIUM' ? 'medium' : 'low'
}

export default function App() {
  const [metric, setMetric] = useState({})
  const [alerts, setAlerts] = useState([])
  const [chart, setChart] = useState([])
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws
    let timer
    const connect = () => {
      ws = new WebSocket(WS)
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        timer = setTimeout(connect, 1500)
      }
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'metric') {
          setMetric(msg.data)
          setChart(prev => [...prev.slice(-39), {
            time: new Date().toLocaleTimeString(),
            rate: +(msg.data.current_error_rate * 100).toFixed(1),
            baseline: +(msg.data.baseline_error_rate * 100).toFixed(1)
          }])
        }
        if (msg.type === 'alert') {
          setAlerts(prev => [msg.data, ...prev.filter(a => a.id !== msg.data.id)].slice(0, 30))
        }
      }
    }
    connect()
    fetch(`${API}/api/alerts`).then(r => r.json()).then(setAlerts).catch(() => {})
    return () => { clearTimeout(timer); ws?.close() }
  }, [])

  const status = metric.system_status === 'anomaly'
    ? 'Anomaly detected'
    : metric.baseline_ready ? 'Monitoring normally' : 'Learning baseline'
  const latest = metric.last_event

  const summary = useMemo(() => {
    const critical = alerts.filter(a => a.severity === 'CRITICAL').length
    const high = alerts.filter(a => a.severity === 'HIGH').length
    return { critical, high }
  }, [alerts])

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <div className="brand"><ShieldAlert size={28}/> SentinelPulse</div>
          <div className="subtitle">Real-time log anomaly detection & alert intelligence</div>
        </div>
        <div className={`connection ${connected ? 'online' : ''}`}>
          <span className="dot"></span>{connected ? 'LIVE' : 'RECONNECTING'}
        </div>
      </header>

      <main>
        <section className="hero">
          <div>
            <div className="eyebrow">OBSERVABILITY COMMAND CENTER</div>
            <h1>Catch incidents before they become outages.</h1>
            <p>SentinelPulse continuously learns normal error behavior, detects abnormal spikes, explains severity, and streams alerts in real time.</p>
          </div>
          <div className="statusCard">
            <Activity size={20}/>
            <div><b>{status}</b><span>Sliding window: {metric.window_size || 20} events</span></div>
          </div>
        </section>

        <section className="cards">
          <Metric title="Current error rate" value={`${((metric.current_error_rate || 0) * 100).toFixed(1)}%`} icon={<Activity/>}/>
          <Metric title="Baseline" value={`${((metric.baseline_error_rate || 0) * 100).toFixed(1)}%`} icon={<Zap/>}/>
          <Metric title="Total events" value={metric.total_events || 0} icon={<Cloud/>}/>
          <Metric title="Alerts" value={alerts.length} icon={<Bell/>}/>
        </section>

        <section className="grid">
          <div className="panel chartPanel">
            <div className="panelHead">
              <div><h2>Error-rate drift</h2><span>Current rate vs learned baseline</span></div>
              <span className="pill">LIVE</span>
            </div>
            <div className="chart"><ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chart}>
                <defs>
                  <linearGradient id="rateFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopOpacity={0.35}/><stop offset="100%" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" opacity={0.12}/>
                <XAxis dataKey="time" hide/>
                <YAxis tickFormatter={v => `${v}%`} width={45}/>
                <Tooltip/>
                <Area type="monotone" dataKey="rate" strokeWidth={3} fill="url(#rateFill)" name="Current"/>
                <Area type="monotone" dataKey="baseline" strokeDasharray="5 5" fill="none" strokeWidth={2} name="Baseline"/>
              </AreaChart>
            </ResponsiveContainer></div>
          </div>

          <div className="panel">
            <div className="panelHead"><div><h2>Live event feed</h2><span>Latest log event</span></div></div>
            <div className="eventBox">
              {latest ? <>
                <div className="eventTop"><span className={`level ${severityClass(latest.level === 'ERROR' ? 'HIGH' : 'LOW')}`}>{latest.level}</span><span>{latest.service}</span></div>
                <code>{latest.message}</code>
                <small>{latest.timestamp}</small>
              </> : <span>Waiting for log events...</span>}
            </div>
            <div className="miniStats">
              <div><b>{summary.critical}</b><span>Critical</span></div>
              <div><b>{summary.high}</b><span>High</span></div>
              <div><b>{metric.total_errors || 0}</b><span>Total errors</span></div>
            </div>
          </div>
        </section>

        <section className="panel alertsPanel">
          <div className="panelHead">
            <div><h2>Alert feed</h2><span>Generated in real time from rolling-window deviation</span></div>
            <div className="legend"><span className="criticalDot"/>Critical <span className="highDot"/>High <span className="mediumDot"/>Medium</div>
          </div>
          <div className="alerts">
            {alerts.length === 0 ? <div className="empty">No anomalies detected yet. Keep the log stream running.</div> :
              alerts.map(a => <div className={`alert ${severityClass(a.severity)}`} key={a.id}>
                <div className="alertIcon"><Bell size={18}/></div>
                <div className="alertBody">
                  <div className="alertTitle"><b>{a.severity} anomaly</b><span>{a.service}</span><time>{new Date(a.timestamp).toLocaleTimeString()}</time></div>
                  <div>Error rate <b>{(a.error_rate*100).toFixed(1)}%</b> vs baseline <b>{(a.baseline_rate*100).toFixed(1)}%</b> · z-score <b>{a.z_score}</b></div>
                  <p>{a.recommendation}</p>
                </div>
              </div>)
            }
          </div>
        </section>
      </main>
    </div>
  )
}

function Metric({title, value, icon}) {
  return <div className="metric"><div className="metricIcon">{icon}</div><div><span>{title}</span><b>{value}</b></div></div>
}
