import { useState } from 'react';
import { useSelector } from 'react-redux';
import type { RootState } from './store';
import { useWebSocket } from './hooks/useWebSocket';
import { LiveMap } from './components/LiveMap';
import { AlertsPanel } from './components/AlertsPanel';
import { SheltersPanel } from './components/SheltersPanel';
import { SOSQueuePanel } from './components/SOSQueuePanel';
import { ResourceTrackingPanel } from './components/ResourceTrackingPanel';
import { Agent7LiaisonPanel } from './components/Agent7LiaisonPanel';
import { DecisionLogPanel } from './components/DecisionLogPanel';
import { DonationsPanel } from './components/DonationsPanel';
import { Shield, Radio, AlertOctagon } from 'lucide-react';

export default function App() {
  // 1. Establish real-time sync with fastapi backend
  useWebSocket();

  const { socketConnected, activeConflicts, alerts } = useSelector((state: RootState) => state.disaster);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'liaison' | 'log' | 'donations'>('dashboard');

  const currentPhase = alerts.length > 0 && alerts[0].disaster_phase ? alerts[0].disaster_phase.toUpperCase() : 'UNKNOWN';

  // Filter for unresolved active conflicts to display EOC warnings
  const pendingConflicts = Object.values(activeConflicts).filter(c => !c.resolved);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-950 font-sans text-slate-100 selection:bg-cyan-500/30">
      
      {/* 1. EMERGENCY COMMAND CENTER HEADER */}
      <header className="flex justify-between items-center bg-slate-900 border-b border-slate-800 px-6 py-3 shrink-0 shadow-lg">
        <div className="flex items-center gap-3">
          <Shield className="w-7 h-7 text-cyan-400 animate-pulse shrink-0" />
          <div>
            <h1 className="font-display font-extrabold text-lg tracking-wider bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              FLOODGUARD COMMUNITY DASHBOARD
            </h1>
            <p className="text-[10px] text-slate-500 font-mono tracking-widest uppercase">
              Lakhimpur Disaster Management EOC Command Center
            </p>
          </div>
        </div>

        {/* Tab Buttons */}
        <nav className="flex gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`px-4 py-1.5 rounded-md text-xs font-semibold tracking-wide transition-colors ${
              activeTab === 'dashboard'
                ? 'bg-cyan-600 text-slate-950 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Command Dashboard
          </button>
          <button
            onClick={() => setActiveTab('liaison')}
            className={`px-4 py-1.5 rounded-md text-xs font-semibold tracking-wide transition-colors ${
              activeTab === 'liaison'
                ? 'bg-cyan-600 text-slate-950 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Liaison Console (Agent 7)
          </button>
          <button
            onClick={() => setActiveTab('log')}
            className={`px-4 py-1.5 rounded-md text-xs font-semibold tracking-wide transition-colors ${
              activeTab === 'log'
                ? 'bg-cyan-600 text-slate-950 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Conflict Log
          </button>
          <button
            onClick={() => setActiveTab('donations')}
            className={`px-4 py-1.5 rounded-md text-xs font-semibold tracking-wide transition-colors ${
              activeTab === 'donations'
                ? 'bg-cyan-600 text-slate-950 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Donations
          </button>
        </nav>

        {/* Status Indicators */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <Radio className={`w-4 h-4 ${socketConnected ? 'text-emerald-400 animate-pulse' : 'text-rose-500 animate-ping'}`} />
            <span className="text-[10px] uppercase font-bold text-slate-400">
              WS API Link:
            </span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
              socketConnected ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border border-rose-500/30 animate-pulse'
            }`}>
              {socketConnected ? 'SYNC ACTIVE' : 'DISCONNECTED'}
            </span>
          </div>
        </div>
      </header>

      {/* 2. REAL-TIME WARNING BANNER (ACTIVE CONFLICT AUCTIONS) */}
      {pendingConflicts.length > 0 && (
        <div className="bg-red-950/80 border-b border-red-800 text-red-200 py-2.5 px-6 shrink-0 flex items-center justify-between shadow-inner animate-pulse">
          <div className="flex items-center gap-3 text-xs">
            <AlertOctagon className="w-5 h-5 text-red-500 shrink-0" />
            <span>
              <strong className="font-bold uppercase tracking-wider text-red-400 mr-2">[Active Resource Conflict]:</strong>
              Agent <strong className="text-red-300 font-mono font-extrabold uppercase">{pendingConflicts[0].agent_a}</strong> and Agent <strong className="text-red-300 font-mono font-extrabold uppercase">{pendingConflicts[0].agent_b}</strong> are competing for contested rescue vehicle <strong className="text-white font-mono">{pendingConflicts[0].resource_name}</strong>. Running priority auction...
            </span>
          </div>
          <span className="text-[9px] font-mono bg-red-900/40 text-red-300 border border-red-700/50 px-2 py-0.5 rounded">
            AUCTION ACTIVE
          </span>
        </div>
      )}

      {/* 3. MAIN WORKSPACE CONTENT */}
      <main className="flex-1 overflow-hidden p-6">
        {activeTab === 'dashboard' && (
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 h-full overflow-hidden">
            {/* Left Panels */}
            <div className="xl:col-span-1 flex flex-col gap-6 overflow-hidden h-full">
              <div className="flex-1 min-h-0">
                <AlertsPanel onNavigateToLiaison={() => setActiveTab('liaison')} />
              </div>
              <div className="flex-1 min-h-0">
                <ResourceTrackingPanel />
              </div>
            </div>

            {/* Map Centric Container */}
            <div className="xl:col-span-2 h-full min-h-[400px]">
              <LiveMap />
            </div>

            {/* Right Panels */}
            <div className="xl:col-span-1 flex flex-col gap-6 overflow-hidden h-full">
              <div className="flex-1 min-h-0">
                <SheltersPanel />
              </div>
              <div className="flex-1 min-h-0">
                <SOSQueuePanel />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'liaison' && (
          <div className="h-full overflow-hidden">
            <Agent7LiaisonPanel />
          </div>
        )}

        {activeTab === 'log' && (
          <div className="h-full overflow-hidden">
            <DecisionLogPanel />
          </div>
        )}

        {activeTab === 'donations' && (
          <div className="h-full overflow-hidden">
            <DonationsPanel />
          </div>
        )}
      </main>

      {/* 4. FOOTER STATUS BAR */}
      <footer className="bg-slate-900 border-t border-slate-800/80 px-6 py-2 shrink-0 flex justify-between items-center text-[10px] text-slate-500 font-mono">
        <div className="flex gap-4">
          <span>SYS MODE: <span className="text-cyan-500 font-bold">MULTI-AGENT COORDINATOR ONLINE</span></span>
          <span className="border-l border-slate-700 pl-4">DISASTER PHASE: <span className="text-orange-400 font-bold">{currentPhase}</span></span>
        </div>
        <div className="flex gap-4">
          <span>TARGET BASIN: RANGANADI RIVER, LAKHIMPUR</span>
          <span>&copy; {new Date().getFullYear()} FLOODGUARD EOC v0.1.0</span>
        </div>
      </footer>

    </div>
  );
}
