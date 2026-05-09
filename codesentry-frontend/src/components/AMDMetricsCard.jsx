/* ═══════════════════════════════════════════════════════════════
   AMDMetricsCard — Live AMD MI300X Performance Metrics
   Displays real-time GPU stats streamed via SSE during scans
   ═══════════════════════════════════════════════════════════════ */

import './AMDMetricsCard.css';

export default function AMDMetricsCard({ amdMetrics, isComplete, scanDuration }) {
  if (!amdMetrics) {
    return (
      <div className="amd-metrics-card">
        <div className="amd-header">
          <div className="amd-header-left">
            <span className="amd-header-icon">⚡</span>
            <span className="amd-header-title">AMD MI300X — Live Performance</span>
          </div>
          <span className="amd-status-dot inactive" />
        </div>
        <div className="amd-connecting">
          <div className="amd-connecting-spinner" />
          <span>Connecting to AMD GPU...</span>
        </div>
        <div className="amd-footer">
          Powered by AMD ROCm + HBM3 Architecture
        </div>
      </div>
    );
  }

  const {
    gpu_utilization_percent = 0,
    vram_used_gb = 0,
    vram_total_gb = 192,
    memory_bandwidth_tbs = 0,
    temperature_c = 0,
    power_draw_w = 0,
    tokens_per_sec = 0,
  } = amdMetrics;

  const vramPercent = vram_total_gb > 0
    ? Math.round((vram_used_gb / vram_total_gb) * 100)
    : 0;

  const tempClass = temperature_c >= 75 ? 'temp-hot' : temperature_c >= 60 ? 'temp-warm' : '';

  return (
    <div className="amd-metrics-card">
      {/* Header */}
      <div className="amd-header">
        <div className="amd-header-left">
          <span className="amd-header-icon">⚡</span>
          <span className="amd-header-title">AMD MI300X — Live Performance</span>
        </div>
        <span className={`amd-status-dot ${isComplete ? 'inactive' : ''}`} />
      </div>

      {/* Completion message */}
      {isComplete && scanDuration && (
        <div className="amd-complete-msg">
          <span>✅</span>
          <span>Scan completed in {scanDuration}s on AMD MI300X</span>
        </div>
      )}

      {/* Stats Grid */}
      <div className="amd-stats-grid">
        {/* GPU Utilization */}
        <div className="amd-stat">
          <span className="amd-stat-label">GPU Utilization</span>
          <span className="amd-stat-value amd-accent">{gpu_utilization_percent}%</span>
        </div>

        {/* VRAM Used */}
        <div className="amd-stat">
          <span className="amd-stat-label">VRAM Used</span>
          <span className="amd-stat-value">{vram_used_gb} <small style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>/ {vram_total_gb} GB</small></span>
          <div className="amd-vram-bar-track">
            <div className="amd-vram-bar-fill" style={{ width: `${vramPercent}%` }} />
          </div>
        </div>

        {/* Memory Bandwidth */}
        <div className="amd-stat">
          <span className="amd-stat-label">Memory Bandwidth</span>
          <span className="amd-stat-value">{memory_bandwidth_tbs} <small style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>TB/s</small></span>
        </div>

        {/* Temperature */}
        <div className="amd-stat">
          <span className="amd-stat-label">Temperature</span>
          <span className={`amd-stat-value ${tempClass}`}>{temperature_c}°C</span>
        </div>

        {/* Power Draw */}
        <div className="amd-stat">
          <span className="amd-stat-label">Power Draw</span>
          <span className="amd-stat-value">{power_draw_w}<small style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>W</small></span>
        </div>

        {/* Inference Speed */}
        <div className="amd-stat">
          <span className="amd-stat-label">Inference Speed</span>
          <span className="amd-stat-value speed-fast">{tokens_per_sec} <small style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>tok/s</small></span>
        </div>
      </div>

      {/* Footer */}
      <div className="amd-footer">
        Powered by AMD ROCm + HBM3 Architecture
      </div>
    </div>
  );
}
