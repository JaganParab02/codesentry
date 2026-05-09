/* ═══════════════════════════════════════════════════════════════
   AgentCard — Status card for each AI agent
   Shows progress, status, and findings count
   ═══════════════════════════════════════════════════════════════ */

import { AGENT_STATUS } from '../context/ScanContext';
import './AgentCard.css';

const AGENT_CONFIG = {
  security: {
    name: 'Security Agent',
    icon: '🔍',
    description: 'Vulnerabilities & threats',
    colorClass: 'agent-security',
    barColor: 'cyan',
  },
  performance: {
    name: 'Performance Agent',
    icon: '⚡',
    description: 'Optimization & efficiency',
    colorClass: 'agent-performance',
    barColor: 'purple',
  },
  fix: {
    name: 'Fix Agent',
    icon: '🔧',
    description: 'Patches & remediation',
    colorClass: 'agent-fix',
    barColor: 'amber',
  },
};

export default function AgentCard({ agentId, agentState }) {
  const config = AGENT_CONFIG[agentId];
  const { status, progress, findingsCount, filesScanned, message } = agentState;

  const statusLabel = {
    [AGENT_STATUS.IDLE]: 'Waiting',
    [AGENT_STATUS.SCANNING]: 'Scanning',
    [AGENT_STATUS.COMPLETE]: 'Complete',
  };

  return (
    <div className={`agent-card glass-card-static ${config.colorClass} ${status}`}>
      <div className="agent-card-header">
        <div className="agent-identity">
          <span className="agent-icon">{config.icon}</span>
          <div>
            <h4 className="agent-name">{config.name}</h4>
            <span className="agent-desc">{config.description}</span>
          </div>
        </div>
        <div className="agent-status-wrapper">
          <span className={`status-dot ${status}`} />
          <span className="agent-status-text">{statusLabel[status]}</span>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="progress-bar-track">
        <div
          className={`progress-bar-fill ${config.barColor}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Stats */}
      <div className="agent-stats">
        <div className="agent-stat">
          <span className="stat-value">{findingsCount}</span>
          <span className="stat-label">{agentId === 'fix' ? 'Fixes' : 'Findings'}</span>
        </div>
        <div className="agent-stat">
          <span className="stat-value">{filesScanned}</span>
          <span className="stat-label">Files</span>
        </div>
        <div className="agent-stat">
          <span className="stat-value">{progress}%</span>
          <span className="stat-label">Progress</span>
        </div>
      </div>

      {/* Status Message */}
      {message && status === AGENT_STATUS.SCANNING && (
        <div className="agent-message">
          <span className="message-dot">›</span>
          <span>{message}</span>
        </div>
      )}
    </div>
  );
}
