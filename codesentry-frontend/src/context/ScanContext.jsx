/* ═══════════════════════════════════════════════════════════════
   ScanContext — Global state management for the scan lifecycle
   ═══════════════════════════════════════════════════════════════ */

import { createContext, useContext, useReducer, useCallback, useRef } from 'react';
import { createScanService } from '../services/scanService';

const ScanContext = createContext(null);

// View states
export const VIEWS = {
  LANDING: 'landing',
  ANALYSIS: 'analysis',
  REPORT: 'report',
};

// Scan states
export const SCAN_STATUS = {
  IDLE: 'idle',
  SCANNING: 'scanning',
  COMPLETE: 'complete',
  ERROR: 'error',
};

// Agent states
export const AGENT_STATUS = {
  IDLE: 'idle',
  SCANNING: 'scanning',
  COMPLETE: 'complete',
};

const initialState = {
  view: VIEWS.LANDING,
  scanStatus: SCAN_STATUS.IDLE,
  scanId: null,
  findings: [],
  fixes: [],
  agents: {
    security: { status: AGENT_STATUS.IDLE, progress: 0, findingsCount: 0, filesScanned: 0, message: '' },
    performance: { status: AGENT_STATUS.IDLE, progress: 0, findingsCount: 0, filesScanned: 0, message: '' },
    fix: { status: AGENT_STATUS.IDLE, progress: 0, findingsCount: 0, filesScanned: 0, message: '' },
  },
  summary: null,
  error: null,
  startTime: null,
  elapsedTime: 0,
  amdMetrics: null,
  amdMigration: null,
};

function scanReducer(state, action) {
  switch (action.type) {
    case 'SET_VIEW':
      return { ...state, view: action.payload };

    case 'SCAN_STARTED':
      return {
        ...state,
        view: VIEWS.ANALYSIS,
        scanStatus: SCAN_STATUS.SCANNING,
        scanId: action.payload.scanId,
        startTime: Date.now(),
        findings: [],
        fixes: [],
        error: null,
        summary: null,
        amdMetrics: null,
        amdMigration: null,
        agents: {
          security: { ...initialState.agents.security },
          performance: { ...initialState.agents.performance },
          fix: { ...initialState.agents.fix },
        },
      };

    case 'AGENT_START':
      return {
        ...state,
        agents: {
          ...state.agents,
          [action.payload.agent]: {
            ...state.agents[action.payload.agent],
            status: AGENT_STATUS.SCANNING,
            message: action.payload.message || 'Initializing...',
          },
        },
      };

    case 'PROGRESS':
      return {
        ...state,
        agents: {
          ...state.agents,
          [action.payload.agent]: {
            ...state.agents[action.payload.agent],
            progress: action.payload.percent,
            filesScanned: action.payload.filesScanned || state.agents[action.payload.agent].filesScanned,
            message: action.payload.message || state.agents[action.payload.agent].message,
            status: action.payload.percent >= 100 ? AGENT_STATUS.COMPLETE : AGENT_STATUS.SCANNING,
          },
        },
      };

    case 'FINDING': {
      const agent = action.payload.agent;
      return {
        ...state,
        findings: [...state.findings, action.payload],
        agents: {
          ...state.agents,
          [agent]: {
            ...state.agents[agent],
            findingsCount: state.agents[agent].findingsCount + 1,
          },
        },
      };
    }

    case 'FIX_READY':
      return {
        ...state,
        fixes: [...state.fixes, action.payload],
        agents: {
          ...state.agents,
          fix: {
            ...state.agents.fix,
            findingsCount: state.agents.fix.findingsCount + 1,
          },
        },
      };

    case 'COMPLETE':
      return {
        ...state,
        scanStatus: SCAN_STATUS.COMPLETE,
        summary: action.payload,
        agents: {
          ...state.agents,
          security: { ...state.agents.security, status: AGENT_STATUS.COMPLETE, progress: 100 },
          performance: { ...state.agents.performance, status: AGENT_STATUS.COMPLETE, progress: 100 },
          fix: { ...state.agents.fix, status: AGENT_STATUS.COMPLETE, progress: 100 },
        },
      };

    case 'ERROR':
      return {
        ...state,
        scanStatus: SCAN_STATUS.ERROR,
        error: action.payload.message,
      };

    case 'UPDATE_ELAPSED':
      return {
        ...state,
        elapsedTime: action.payload,
      };

    case 'AMD_METRICS':
      return {
        ...state,
        amdMetrics: action.payload,
      };

    case 'AMD_MIGRATION_FINDING': {
      const prev = state.amdMigration || { findings: [], compatibility_score: 100, compatibility_label: 'Analyzing...', total_cuda_patterns_found: 0, summary: '' };
      return {
        ...state,
        amdMigration: {
          ...prev,
          findings: [...prev.findings, action.payload],
          total_cuda_patterns_found: prev.total_cuda_patterns_found + 1,
        },
      };
    }

    case 'AMD_MIGRATION_SUMMARY':
      return {
        ...state,
        amdMigration: {
          ...(state.amdMigration || { findings: [] }),
          ...action.payload,
        },
      };

    case 'RESET':
      return { ...initialState };

    default:
      return state;
  }
}

export function ScanProvider({ children }) {
  const [state, dispatch] = useReducer(scanReducer, initialState);
  const serviceRef = useRef(null);
  const timerRef = useRef(null);

  const startScan = useCallback(async (payload) => {
    // Cleanup previous scan
    if (serviceRef.current) {
      serviceRef.current.destroy();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    const service = createScanService();
    serviceRef.current = service;

    // Wire up event handlers
    service.on('scan_started', (data) => {
      dispatch({ type: 'SCAN_STARTED', payload: data });

      // Start elapsed time counter
      const start = Date.now();
      timerRef.current = setInterval(() => {
        dispatch({ type: 'UPDATE_ELAPSED', payload: Date.now() - start });
      }, 100);
    });

    service.on('agent_start', (data) => {
      dispatch({ type: 'AGENT_START', payload: data });
    });

    service.on('progress', (data) => {
      dispatch({ type: 'PROGRESS', payload: data });
    });

    service.on('finding', (data) => {
      dispatch({ type: 'FINDING', payload: data });
    });

    service.on('fix_ready', (data) => {
      dispatch({ type: 'FIX_READY', payload: data });
    });

    service.on('amd_metrics', (data) => {
      dispatch({ type: 'AMD_METRICS', payload: data });
    });

    service.on('amd_migration_finding', (data) => {
      dispatch({ type: 'AMD_MIGRATION_FINDING', payload: data });
    });

    service.on('amd_migration_summary', (data) => {
      dispatch({ type: 'AMD_MIGRATION_SUMMARY', payload: data });
    });

    service.on('complete', (data) => {
      console.log('[ScanContext] COMPLETE event received — triggering notification');
      dispatch({ type: 'COMPLETE', payload: data });
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }

      // Handle Notification / Toast
      console.log("[ScanContext] Notification permission status:", Notification.permission);
      if ('Notification' in window && Notification.permission === 'granted') {
        try {
          console.log("[ScanContext] Attempting to show native notification...");
          const notification = new Notification("✅ CodeSentry Analysis Complete", {
            body: "Your code scan is done. Open the report to review findings.",
            tag: "codesentry-scan-complete", // Prevents duplicate notifications
            requireInteraction: true // Keeps it visible until user interacts
          });
          notification.onclick = function() {
            window.focus();
            dispatch({ type: 'SET_VIEW', payload: VIEWS.REPORT });
            this.close();
          };
        } catch (e) {
          console.error("[ScanContext] Native Notification failed:", e);
        }
      }
      
      // Always show the in-app toast to guarantee visibility
      // Play a subtle notification sound
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.value = 880;
        osc.type = 'sine';
        gain.gain.value = 0.15;
        osc.start();
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.3);
        osc.stop(audioCtx.currentTime + 0.3);
      } catch(e) { /* audio not critical */ }

      const toast = document.createElement('div');
      toast.id = 'codesentry-complete-toast';
      toast.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px;">
          <span style="font-size: 1.8rem;">✅</span>
          <div>
            <h4 style="margin: 0; color: #e2e8f0; font-size: 1rem; font-weight: 600;">CodeSentry Analysis Complete</h4>
            <p style="margin: 4px 0 0; font-size: 0.85rem; color: #94a3b8;">Your code scan is done. Click to view report.</p>
          </div>
        </div>
      `;
      
      Object.assign(toast.style, {
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        padding: '16px 20px',
        borderRadius: '12px',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(56, 189, 248, 0.3)',
        border: '1px solid rgba(56, 189, 248, 0.4)',
        background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
        zIndex: '99999',
        transform: 'translateY(120px)',
        opacity: '0',
        transition: 'all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
        cursor: 'pointer',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        minWidth: '320px',
        backdropFilter: 'blur(12px)',
      });

      document.body.appendChild(toast);

      // Animate in
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          toast.style.transform = 'translateY(0)';
          toast.style.opacity = '1';
        });
      });

      // Click to view report and dismiss
      toast.onclick = () => {
        dispatch({ type: 'SET_VIEW', payload: VIEWS.REPORT });
        toast.style.transform = 'translateY(120px)';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 400);
      };

      // Auto remove after 8 seconds
      setTimeout(() => {
        if (document.body.contains(toast)) {
          toast.style.transform = 'translateY(120px)';
          toast.style.opacity = '0';
          setTimeout(() => toast.remove(), 400);
        }
      }, 8000);
    });

    service.on('error', (data) => {
      dispatch({ type: 'ERROR', payload: data });
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    });

    // Request Notification permission if supported and not already granted/denied
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    // Start the scan
    await service.startScan(payload);
  }, []);

  const resetScan = useCallback(() => {
    if (serviceRef.current) {
      serviceRef.current.destroy();
      serviceRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    dispatch({ type: 'RESET' });
  }, []);

  const setView = useCallback((view) => {
    dispatch({ type: 'SET_VIEW', payload: view });
  }, []);

  const value = {
    ...state,
    startScan,
    resetScan,
    setView,
  };

  return (
    <ScanContext.Provider value={value}>
      {children}
    </ScanContext.Provider>
  );
}

export function useScan() {
  const context = useContext(ScanContext);
  if (!context) {
    throw new Error('useScan must be used within a ScanProvider');
  }
  return context;
}
