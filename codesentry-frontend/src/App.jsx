/* ═══════════════════════════════════════════════════════════════
   App.jsx — Root component with view routing
   ═══════════════════════════════════════════════════════════════ */

import { ScanProvider, useScan, VIEWS } from './context/ScanContext';
import LandingPage from './components/LandingPage';
import AnalysisView from './components/AnalysisView';
import ReportView from './components/ReportView';

function AppContent() {
  const { view } = useScan();

  return (
    <>
      {/* Subtle scanline overlay for cyberpunk feel */}
      <div className="scanline-overlay" />

      {view === VIEWS.LANDING && <LandingPage />}
      {view === VIEWS.ANALYSIS && <AnalysisView />}
      {view === VIEWS.REPORT && <ReportView />}
    </>
  );
}

function App() {
  return (
    <ScanProvider>
      <AppContent />
    </ScanProvider>
  );
}

export default App;
