/* ═══════════════════════════════════════════════════════════════
   LandingPage — Hero section with GitHub URL input & code paste
   ═══════════════════════════════════════════════════════════════ */

import { useState } from 'react';
import { useScan } from '../context/ScanContext';
import ParticleBackground from './ParticleBackground';
import './LandingPage.css';

export default function LandingPage() {
  const { startScan } = useScan();
  const [inputMode, setInputMode] = useState('url'); // 'url' or 'code'
  const [githubUrl, setGithubUrl] = useState('');
  const [codeInput, setCodeInput] = useState('');
  const [language, setLanguage] = useState('javascript');
  const [isStarting, setIsStarting] = useState(false);

  const canScan = inputMode === 'url' ? githubUrl.trim().length > 0 : codeInput.trim().length > 0;

    const handleScan = async () => {
    if (!canScan || isStarting) return;
    
    // Request Notification permission on user gesture
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    setIsStarting(true);

    const sessionId = `cs-${Math.random().toString(36).substring(2, 11)}-${Date.now()}`;
    
    let sourceType = 'github';
    if (inputMode === 'url') {
      if (githubUrl.includes('huggingface.co')) {
        sourceType = 'huggingface';
      }
    } else {
      sourceType = 'code';
    }

    const payload = inputMode === 'url'
      ? { 
          source_type: sourceType, 
          source: githubUrl.trim(),
          session_id: sessionId
        }
      : { 
          source_type: sourceType, 
          source: codeInput.trim(),
          session_id: sessionId
        };

    await startScan(payload);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && inputMode === 'url') {
      e.preventDefault();
      handleScan();
    }
  };

  return (
    <div className="landing-page">
      <div className="vignette-overlay" />
      <div className="ambient-light" />
      <ParticleBackground />

      {/* Header */}
      <header className="landing-header">
        <div className="header-logo">
          <span className="shield-icon">🛡️</span>
          <span className="logo-text">CodeSentry</span>
        </div>

      </header>

      {/* Hero */}
      <main className="landing-main">
        <div className="hero-section">
          <div className="hero-badge animate-fade-in">
            <span className="status-dot scanning" />
            <span>AI-Powered Security Intelligence</span>
          </div>

          <h1 className="hero-title animate-fade-in-up">
            Secure Your Code<br />
            <span className="hero-gradient">Before It Ships</span>
          </h1>

          <p className="hero-subtitle animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            3 AI agents analyze your codebase in real-time — detecting vulnerabilities,
            finding performance issues, and generating fixes. All locally, all privately.
          </p>

          {/* Privacy Banner */}
          <div className="privacy-banner animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <span>🔒</span>
            <span>Your code never leaves this machine — 100% local inference, zero data retention</span>
          </div>
        </div>

        {/* Input Section */}
        <div className="input-section animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          {/* Mode Tabs */}
          <div className="input-tabs">
            <button
              id="tab-github-url"
              className={`input-tab ${inputMode === 'url' ? 'active' : ''}`}
              onClick={() => setInputMode('url')}
            >
              <span>🐙/🤗</span> Repo URL
            </button>
            <button
              id="tab-paste-code"
              className={`input-tab ${inputMode === 'code' ? 'active' : ''}`}
              onClick={() => setInputMode('code')}
            >
              <span>📋</span> Paste Code
            </button>
          </div>

          {/* Input Area */}
          <div className="input-area glass-card-static">
            {inputMode === 'url' ? (
              <div className="url-input-wrapper">
                <div className="input-icon">🔗</div>
                <input
                  id="github-url-input"
                  type="url"
                  className="input-field"
                  placeholder="https://github.com/owner/repo or https://huggingface.co/spaces/owner/repo"
                  value={githubUrl}
                  onChange={(e) => setGithubUrl(e.target.value)}
                  onKeyDown={handleKeyDown}
                  autoFocus
                />
              </div>
            ) : (
              <div className="code-input-wrapper">
                <div className="code-input-header">
                  <select
                    id="language-select"
                    className="language-select"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  >
                    <option value="javascript">JavaScript</option>
                    <option value="python">Python</option>
                    <option value="typescript">TypeScript</option>
                    <option value="java">Java</option>
                    <option value="go">Go</option>
                    <option value="rust">Rust</option>
                    <option value="cpp">C++</option>
                    <option value="csharp">C#</option>
                  </select>
                  <span className="line-count mono text-secondary">
                    {codeInput.split('\n').filter(l => l.trim()).length} lines
                  </span>
                </div>
                <textarea
                  id="code-paste-editor"
                  className="code-editor"
                  placeholder="// Paste your code here for analysis...&#10;&#10;const express = require('express');&#10;const app = express();&#10;&#10;app.get('/user/:id', async (req, res) => {&#10;  const query = `SELECT * FROM users WHERE id = '${req.params.id}'`;&#10;  // ...&#10;});"
                  value={codeInput}
                  onChange={(e) => setCodeInput(e.target.value)}
                  spellCheck={false}
                />
              </div>
            )}
          </div>

          {/* Scan Button */}
          <button
            id="scan-button"
            className={`scan-btn ${canScan ? 'animate-glow' : ''}`}
            onClick={handleScan}
            disabled={!canScan || isStarting}
          >
            {isStarting ? (
              <>
                <span className="scan-spinner">⟳</span>
                <span>Initializing Agents...</span>
              </>
            ) : (
              <>
                <span className="scan-icon">⚡</span>
                <span>Launch Security Scan</span>
              </>
            )}
          </button>
        </div>

        {/* Feature Cards */}
        <div className="features-grid animate-fade-in-up" style={{ animationDelay: '0.5s' }}>
          <div className="feature-card glass-card">
            <div className="feature-icon agent-security">🔍</div>
            <h4>Security Agent</h4>
            <p>OWASP vulnerabilities, prompt injection, hardcoded secrets, auth weaknesses</p>
          </div>
          <div className="feature-card glass-card">
            <div className="feature-icon agent-performance">⚡</div>
            <h4>Performance Agent</h4>
            <p>Memory leaks, N+1 queries, GPU inefficiencies, tensor optimization</p>
          </div>
          <div className="feature-card glass-card">
            <div className="feature-icon agent-fix">🔧</div>
            <h4>Fix Agent</h4>
            <p>AI-generated patches, before/after diffs, secure code suggestions</p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="footer-content">
          <span className="footer-powered">
            Powered by <strong>Qwen</strong> · Built on <strong>AMD</strong>
          </span>
          <span className="footer-divider">•</span>
          <span className="text-secondary">Privacy-First AI Security</span>
        </div>
      </footer>
    </div>
  );
}
