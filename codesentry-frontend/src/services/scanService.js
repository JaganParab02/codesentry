/* ═══════════════════════════════════════════════════════════════
   Scan Service — Unified interface for mock and live SSE
   Automatically switches based on VITE_MOCK_MODE env variable
   ═══════════════════════════════════════════════════════════════ */

import { createMockService } from './mockService';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export class ScanService {
  constructor() {
    this.mockService = null;
    this.eventSource = null;
    this.eventHandlers = {};
  }

  on(eventType, handler) {
    if (!this.eventHandlers[eventType]) {
      this.eventHandlers[eventType] = [];
    }
    this.eventHandlers[eventType].push(handler);
    return this;
  }

  emit(eventType, data) {
    const handlers = this.eventHandlers[eventType] || [];
    handlers.forEach(handler => handler(data));
  }

  async startScan(payload) {
    if (IS_MOCK) {
      return this._startMockScan(payload);
    }
    return this._startLiveScan(payload);
  }

  async _startMockScan(payload) {
    this.mockService = createMockService();

    // Forward all events from mock service
    const eventTypes = [
      'scan_started', 'agent_start', 'finding', 'progress',
      'fix_ready', 'complete', 'error', 'event',
      'amd_metrics', 'amd_migration_finding', 'amd_migration_summary',
    ];

    eventTypes.forEach(type => {
      this.mockService.on(type, (data) => this.emit(type, data));
    });

    await this.mockService.startScan(payload);
  }

  async _startLiveScan(payload) {
    try {
      // POST to initiate scan
      const response = await fetch(`${API_URL}/api/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error('Scan initiation failed');

      const { scanId } = await response.json();
      this.emit('scan_started', { scanId });

      // Open SSE connection
      this.eventSource = new EventSource(`${API_URL}/api/scan/stream/${scanId}`);

      this.eventSource.addEventListener('agent_start', (e) => {
        this.emit('agent_start', JSON.parse(e.data));
      });

      this.eventSource.addEventListener('finding', (e) => {
        this.emit('finding', JSON.parse(e.data));
      });

      this.eventSource.addEventListener('progress', (e) => {
        this.emit('progress', JSON.parse(e.data));
      });

      this.eventSource.addEventListener('fix_ready', (e) => {
        this.emit('fix_ready', JSON.parse(e.data));
      });

      this.eventSource.addEventListener('complete', (e) => {
        console.log('[ScanService] SSE complete event received');
        this.emit('complete', JSON.parse(e.data));
        this.eventSource.close();
      });

      this.eventSource.addEventListener('amd_metrics', (e) => {
        this.emit('amd_metrics', JSON.parse(e.data));
      });

      this.eventSource.addEventListener('amd_migration_finding', (e) => {
        this.emit('amd_migration_finding', JSON.parse(e.data));
      });

      this.eventSource.addEventListener('amd_migration_summary', (e) => {
        this.emit('amd_migration_summary', JSON.parse(e.data));
      });

      // Backend custom SSE 'error' event (different from connection onerror)
      this.eventSource.addEventListener('error', (e) => {
        // Custom SSE events have a 'data' property; connection errors don't
        if (e.data) {
          console.log('[ScanService] SSE error event from backend:', e.data);
          this.emit('error', JSON.parse(e.data));
          this.eventSource.close();
        }
      });

      this.eventSource.onerror = (e) => {
        // Only emit connection error if the EventSource is not already closed
        if (this.eventSource && this.eventSource.readyState === EventSource.CLOSED) {
          return; // Already closed by complete/error handler above
        }
        this.emit('error', { message: 'Connection to scan server lost' });
        this.eventSource.close();
      };

    } catch (error) {
      this.emit('error', { message: error.message });
    }
  }

  stop() {
    if (this.mockService) {
      this.mockService.stop();
      this.mockService = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  destroy() {
    this.stop();
    this.eventHandlers = {};
  }
}

export function createScanService() {
  return new ScanService();
}
