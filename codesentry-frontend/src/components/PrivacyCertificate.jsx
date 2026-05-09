import './PrivacyCertificate.css';

export default function PrivacyCertificate({ scanId }) {
  const sessionId = scanId || `cs-${Date.now().toString(36)}`;
  const timestamp = new Date().toLocaleString();

  return (
    <div className="privacy-certificate glass-card-static">
      <div className="cert-header">
        <div className="cert-shield">🛡️</div>
        <div>
          <h3 className="cert-title">Privacy Certificate</h3>
          <p className="cert-subtitle">Zero-Trust Security Guarantee</p>
        </div>
      </div>

      <div className="cert-body">
        <div className="cert-guarantees">
          <div className="cert-item">
            <span className="cert-check">✅</span>
            <div>
              <strong>Local Inference Only</strong>
              <p>All AI analysis performed on-device using local models</p>
            </div>
          </div>
          <div className="cert-item">
            <span className="cert-check">✅</span>
            <div>
              <strong>Zero Data Retention</strong>
              <p>No code or analysis data stored after session ends</p>
            </div>
          </div>
          <div className="cert-item">
            <span className="cert-check">✅</span>
            <div>
              <strong>No External API Calls</strong>
              <p>Your code never leaves this machine during analysis</p>
            </div>
          </div>
          <div className="cert-item">
            <span className="cert-check">✅</span>
            <div>
              <strong>Session Data Wiped</strong>
              <p>All temporary data cleared upon scan completion</p>
            </div>
          </div>
        </div>

        <div className="cert-meta">
          <div className="cert-meta-item">
            <span className="cert-meta-label">Session ID</span>
            <span className="cert-meta-value mono">{sessionId}</span>
          </div>
          <div className="cert-meta-item">
            <span className="cert-meta-label">Timestamp</span>
            <span className="cert-meta-value mono">{timestamp}</span>
          </div>
          <div className="cert-meta-item">
            <span className="cert-meta-label">Engine</span>
            <span className="cert-meta-value mono">Qwen2.5-Coder (Local)</span>
          </div>
        </div>
      </div>

      <div className="cert-footer">
        <span>🔒 Enterprise-Grade Privacy • CodeSentry</span>
      </div>
    </div>
  );
}
