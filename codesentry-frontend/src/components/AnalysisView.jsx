/* ═══════════════════════════════════════════════════════════════
   AnalysisView — Live analysis split-panel dashboard
   Left: Agent status cards | Right: Live findings feed
   ═══════════════════════════════════════════════════════════════ */

import { useEffect, useRef, useMemo } from 'react';
import { useScan, SCAN_STATUS, VIEWS } from '../context/ScanContext';
import AgentCard from './AgentCard';
import FindingCard from './FindingCard';
import AMDMetricsCard from './AMDMetricsCard';
import './AnalysisView.css';

function formatTime(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

export default function AnalysisView() {
  const {
    scanStatus, agents, findings, fixes, elapsedTime,
    summary, setView, resetScan, amdMetrics,
  } = useScan();

  const feedRef = useRef(null);

  // Auto-scroll findings feed
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [findings, fixes]);

  // Build fix map for quick lookup
  const fixMap = useMemo(() => {
    const map = {};
    fixes.forEach(fix => {
      map[fix.findingId] = fix;
    });
    return map;
  }, [fixes]);

  // Severity counts
  const severityCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    findings.forEach(f => {
      if (counts[f.severity] !== undefined) counts[f.severity]++;
    });
    return counts;
  }, [findings]);

  const isComplete = scanStatus === SCAN_STATUS.COMPLETE;

  return (
    <div className="analysis-view">
      {/* Header Bar */}
      <header className="header-bar">
        <div className="header-logo" onClick={resetScan} style={{ cursor: 'pointer' }}>
          <span className="shield-icon">🛡️</span>
          <span className="logo-text">CodeSentry</span>
        </div>

        <div className="header-center">
          <div className="scan-status-indicator">
            <span className={`status-dot ${isComplete ? 'complete' : 'scanning'}`} />
            <span className="mono" style={{ fontSize: '0.8rem' }}>
              {isComplete ? 'SCAN COMPLETE' : 'SCANNING...'}
            </span>
          </div>
          <span className="elapsed-time mono">{formatTime(elapsedTime)}</span>
        </div>

        <div className="header-actions">
          {isComplete && (
            <button
              id="view-report-btn"
              className="btn btn-primary btn-sm"
              onClick={() => setView(VIEWS.REPORT)}
            >
              📊 View Report
            </button>
          )}
          <button
            id="new-scan-btn"
            className="btn btn-ghost btn-sm"
            onClick={resetScan}
          >
            ↻ New Scan
          </button>
        </div>
      </header>

      {/* Main Split Panel */}
      <div className="split-panel">
        {/* Left Panel — Agent Status */}
        <aside className="agents-panel">
          <div className="panel-header">
            <h3>AI Agents</h3>
            <span className="tag">{Object.values(agents).filter(a => a.status === 'complete').length}/3</span>
          </div>

          <div className="agents-list">
            <AgentCard agentId="security" agentState={agents.security} />
            <AgentCard agentId="performance" agentState={agents.performance} />
            <AgentCard agentId="fix" agentState={agents.fix} />
          </div>

          {/* Live Stats Summary */}
          <div className="live-stats glass-card-static">
            <div className="live-stats-header">
              <span>📊</span>
              <span>Live Statistics</span>
            </div>
            <div className="stats-grid">
              <div className="live-stat">
                <span className="live-stat-value text-critical">{severityCounts.critical}</span>
                <span className="live-stat-label">Critical</span>
              </div>
              <div className="live-stat">
                <span className="live-stat-value text-high">{severityCounts.high}</span>
                <span className="live-stat-label">High</span>
              </div>
              <div className="live-stat">
                <span className="live-stat-value text-medium">{severityCounts.medium}</span>
                <span className="live-stat-label">Medium</span>
              </div>
              <div className="live-stat">
                <span className="live-stat-value text-low">{severityCounts.low}</span>
                <span className="live-stat-label">Low</span>
              </div>
            </div>
            <div className="total-findings">
              <span>Total findings:</span>
              <strong>{findings.length}</strong>
            </div>
            <div className="total-findings">
              <span>Fixes generated:</span>
              <strong className="text-low">{fixes.length}</strong>
            </div>
          </div>

          {/* AMD MI300X Live Metrics */}
          <AMDMetricsCard
            amdMetrics={amdMetrics}
            isComplete={isComplete}
            scanDuration={isComplete ? Math.round(elapsedTime / 1000) : null}
          />
        </aside>

        {/* Right Panel — Live Findings Feed */}
        <main className="findings-panel" ref={feedRef}>
          <div className="panel-header">
            <h3>Live Findings</h3>
            <span className="findings-count mono">{findings.length} findings</span>
          </div>

          {findings.length === 0 && (
            <div className="empty-state">
              <div className="icon">🔍</div>
              <p>Waiting for agents to report findings...</p>
              <div className="scanning-indicator">
                <div className="progress-bar-track" style={{ width: '200px' }}>
                  <div className="progress-bar-fill cyan" style={{ width: '60%' }} />
                </div>
              </div>
            </div>
          )}

          <div className="findings-feed">
            {findings.map((finding, index) => (
              <FindingCard
                key={finding.id || index}
                finding={finding}
                index={index}
                fix={fixMap[finding.id]}
              />
            ))}

            {/* Fix events shown as special cards */}
            {fixes.filter(fix => !findings.find(f => f.id === fix.findingId)).map((fix, index) => (
              <div key={`fix-${index}`} className="fix-event-card glass-card-static animate-slide-in">
                <div className="fix-event-header">
                  <span>🔧</span>
                  <span className="fix-event-title">{fix.title}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Completion Banner */}
          {isComplete && (
            <div className="completion-banner glass-card animate-fade-in-up">
              <div className="completion-icon">✅</div>
              <div className="completion-content">
                <h4>Analysis Complete</h4>
                <p>
                  Found {summary?.totalFindings || findings.length} issues across {summary?.filesAnalyzed || '24'} files
                  in {formatTime(elapsedTime)}. {fixes.length} automated fixes generated.
                </p>
              </div>
              <button
                className="btn btn-primary"
                onClick={() => setView(VIEWS.REPORT)}
              >
                📊 View Full Report
              </button>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
