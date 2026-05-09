import { useMemo } from 'react';
import { Doughnut } from 'react-chartjs-2';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';

ChartJS.register(ArcElement, Tooltip, Legend);

export default function SeverityChart({ counts }) {
  const data = useMemo(() => ({
    labels: ['Critical', 'High', 'Medium', 'Low'],
    datasets: [{
      data: [counts.critical, counts.high, counts.medium, counts.low],
      backgroundColor: [
        'rgba(255, 45, 85, 0.8)',
        'rgba(255, 107, 53, 0.8)',
        'rgba(255, 184, 0, 0.8)',
        'rgba(0, 255, 136, 0.8)',
      ],
      borderColor: [
        'rgba(255, 45, 85, 1)',
        'rgba(255, 107, 53, 1)',
        'rgba(255, 184, 0, 1)',
        'rgba(0, 255, 136, 1)',
      ],
      borderWidth: 2,
      hoverOffset: 8,
    }],
  }), [counts]);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '65%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#8a94a8',
          font: { family: "'JetBrains Mono', monospace", size: 11 },
          padding: 16,
          usePointStyle: true,
        },
      },
      tooltip: {
        backgroundColor: '#0d1225',
        titleColor: '#e8ecf4',
        bodyColor: '#8a94a8',
        borderColor: 'rgba(0, 240, 255, 0.2)',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
      },
    },
  };

  const total = counts.critical + counts.high + counts.medium + counts.low;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <Doughnut data={data} options={options} />
      <div style={{
        position: 'absolute', top: '42%', left: '50%',
        transform: 'translate(-50%, -50%)', textAlign: 'center',
        pointerEvents: 'none',
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '2rem', fontWeight: 700, color: '#e8ecf4',
        }}>{total}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '0.65rem', color: '#5a6478',
          textTransform: 'uppercase', letterSpacing: '0.1em',
        }}>Findings</div>
      </div>
    </div>
  );
}
