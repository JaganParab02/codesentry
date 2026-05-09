/* ═══════════════════════════════════════════════════════════════
   FindingCard — Expandable finding card with severity + code
   ═══════════════════════════════════════════════════════════════ */

import { useState } from 'react';
import SeverityBadge from './SeverityBadge';
import './FindingCard.css';

const AGENT_ICONS = {
  security: '🔍',
  performance: '⚡',
  fix: '🔧',
};

export default function FindingCard({ finding, index, fix }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`finding-card glass-card-static animate-slide-in`}
      style={{ animationDelay: `${index * 0.05}s` }}
    >
      <div
        className="finding-card-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="finding-header-left">
          <SeverityBadge severity={finding.severity} />
          <span className="finding-agent-icon" title={`${finding.agent} agent`}>
            {AGENT_ICONS[finding.agent] || '🔍'}
          </span>
        </div>
        <div className="finding-header-right">
          {finding.cwe && <span className="tag">{finding.cwe}</span>}
          <button className="expand-btn" aria-label="Toggle details">
            {isExpanded ? '▾' : '▸'}
          </button>
        </div>
      </div>

      <div className="finding-title-row">
        <h4 className="finding-title">{finding.title}</h4>
        {finding.id && <span className="finding-id mono">{finding.id}</span>}
      </div>

      <p className="finding-description">{finding.description}</p>

      {finding.file && (
        <div className="finding-location">
          <span className="location-icon">📄</span>
          <span className="location-path mono">{finding.file}</span>
          {finding.line && <span className="location-line mono">:{finding.line}</span>}
        </div>
      )}

      {/* Expanded Details */}
      {isExpanded && (
        <div className="finding-details animate-fade-in">
          {/* Code Snippet */}
          {finding.code && (
            <div className="finding-code-section">
              <div className="code-section-label">Vulnerable Code</div>
              <div className="code-block">
                <pre><code>{finding.code}</code></pre>
              </div>
            </div>
          )}

          {/* Suggestion */}
          {finding.suggestion && (
            <div className="finding-suggestion">
              <div className="code-section-label">💡 Recommendation</div>
              <p>{finding.suggestion}</p>
            </div>
          )}

          {/* Fix Preview */}
          {fix && (
            <div className="finding-fix-preview">
              <div className="code-section-label">🔧 AI-Generated Fix</div>
              <div className="diff-container">
                <div className="diff-panel diff-before">
                  <div className="diff-header">Before</div>
                  <div className="code-block">
                    <pre><code>{fix.before}</code></pre>
                  </div>
                </div>
                <div className="diff-arrow">→</div>
                <div className="diff-panel diff-after">
                  <div className="diff-header">After</div>
                  <div className="code-block">
                    <pre><code>{fix.after}</code></pre>
                  </div>
                </div>
              </div>
              {fix.explanation && (
                <p className="fix-explanation">{fix.explanation}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Quick action bar */}
      <div className="finding-actions">
        {finding.fixAvailable && !fix && (
          <span className="fix-available-tag">
            <span>🔧</span> Fix available
          </span>
        )}
        {fix && (
          <span className="fix-ready-tag">
            <span>✅</span> Fix generated
          </span>
        )}
      </div>
    </div>
  );
}
