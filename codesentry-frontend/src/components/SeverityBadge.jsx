/* ═══════════════════════════════════════════════════════════════
   SeverityBadge — Styled severity indicator
   CRITICAL pulses, HIGH glows, MEDIUM/LOW static
   ═══════════════════════════════════════════════════════════════ */

export default function SeverityBadge({ severity }) {
  const severityConfig = {
    critical: { label: 'CRITICAL', icon: '🔴' },
    high: { label: 'HIGH', icon: '🟠' },
    medium: { label: 'MEDIUM', icon: '🟡' },
    low: { label: 'LOW', icon: '🟢' },
    info: { label: 'INFO', icon: '🔵' },
  };

  const config = severityConfig[severity] || severityConfig.info;

  return (
    <span className={`severity-badge severity-${severity}`}>
      <span>{config.icon}</span>
      <span>{config.label}</span>
    </span>
  );
}
