/* ═══════════════════════════════════════════════════════════════
   Mock SSE Service — Replay engine for demo mode
   Replays mock_analysis.json events with realistic timing
   ═══════════════════════════════════════════════════════════════ */

const SPEED_MULTIPLIER = 1; // Set < 1 to speed up, > 1 to slow down

export class MockSSEService {
  constructor() {
    this.timeouts = [];
    this.isRunning = false;
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
    this.isRunning = true;
    this.timeouts = [];

    try {
      const response = await fetch('/mock_analysis.json');
      const mockData = await response.json();

      // Emit scan started
      this.emit('scan_started', {
        scanId: mockData.meta.scanId,
        filesAnalyzed: mockData.meta.filesAnalyzed,
        linesScanned: mockData.meta.linesScanned,
      });

      // ── Simulated AMD metrics (every 2 seconds) ──
      const metricsInterval = setInterval(() => {
        if (!this.isRunning) { clearInterval(metricsInterval); return; }
        this.emit('amd_metrics', {
          gpu_utilization_percent: Math.floor(78 + Math.random() * 16),
          vram_used_gb: +(44 + Math.random() * 8).toFixed(1),
          vram_total_gb: 192.0,
          temperature_c: Math.floor(58 + Math.random() * 9),
          power_draw_w: Math.floor(580 + Math.random() * 70),
          memory_bandwidth_tbs: +(4.2 + Math.random() * 0.9).toFixed(1),
          tokens_per_sec: Math.floor(1100 + Math.random() * 300),
          timestamp: new Date().toISOString(),
        });
      }, 2000);
      this.timeouts.push(metricsInterval);

      // Schedule each event with its delay
      mockData.events.forEach((event) => {
        const delay = event.delay * SPEED_MULTIPLIER;
        const timeout = setTimeout(() => {
          if (!this.isRunning) return;

          this.emit(event.type, {
            agent: event.agent,
            ...event.data,
          });

          // Also emit a generic 'event' for logging
          this.emit('event', {
            type: event.type,
            agent: event.agent,
            ...event.data,
          });
        }, delay);

        this.timeouts.push(timeout);
      });

      // ── Simulated AMD migration findings (after perf agent) ──
      const migrationDelay = (mockData.events.length > 0
        ? Math.max(...mockData.events.map(e => e.delay)) - 3000
        : 8000) * SPEED_MULTIPLIER;

      const migTimeout = setTimeout(() => {
        if (!this.isRunning) return;
        const mockMigrationFindings = [
          { id: 'AMD_M02', title: 'NVIDIA-Specific CLI Tool', description: 'nvidia-smi is NVIDIA-only and will fail on AMD hardware.', rocm_fix: "Replace nvidia-smi with rocm-smi. Example: subprocess.run(['rocm-smi', '--showmeminfo', 'vram'])", severity: 'critical', file: 'monitor.py', line: 42, code_snippet: '>>> 42 | subprocess.run(["nvidia-smi"])' },
          { id: 'AMD_M03', title: 'CUDA Device Selection Environment Variable', description: 'CUDA_VISIBLE_DEVICES is ignored on AMD/ROCm hardware.', rocm_fix: 'Replace with HIP_VISIBLE_DEVICES=0 for AMD GPU selection.', severity: 'high', file: 'config.py', line: 15, code_snippet: '>>> 15 | os.environ["CUDA_VISIBLE_DEVICES"] = "0"' },
          { id: 'AMD_M05', title: 'FP16 Precision (Suboptimal on MI300X)', description: 'FP16 works on AMD but bfloat16 is natively supported on MI300X.', rocm_fix: 'Replace .half() with .bfloat16() and torch.float16 with torch.bfloat16.', severity: 'medium', file: 'model.py', line: 28, code_snippet: '>>> 28 | model = model.half()' },
        ];
        mockMigrationFindings.forEach((f, i) => {
          setTimeout(() => {
            if (!this.isRunning) return;
            this.emit('amd_migration_finding', f);
          }, i * 300);
        });
        setTimeout(() => {
          if (!this.isRunning) return;
          this.emit('amd_migration_summary', {
            compatibility_score: 57,
            compatibility_label: 'Needs Migration Work',
            total_cuda_patterns_found: 3,
            summary: 'Found 3 CUDA-specific patterns. After applying fixes, this codebase will be fully optimized for AMD MI300X.',
          });
        }, mockMigrationFindings.length * 300 + 200);
      }, Math.max(migrationDelay, 5000));
      this.timeouts.push(migTimeout);

    } catch (error) {
      console.error('Mock SSE: Failed to load mock data', error);
      this.emit('error', { message: 'Failed to load mock analysis data' });
    }
  }

  stop() {
    this.isRunning = false;
    this.timeouts.forEach(t => clearTimeout(t));
    this.timeouts = [];
  }

  destroy() {
    this.stop();
    this.eventHandlers = {};
  }
}

export function createMockService() {
  return new MockSSEService();
}
