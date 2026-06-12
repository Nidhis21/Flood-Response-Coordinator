import { useSelector } from 'react-redux';
import type { RootState } from '../store';
import { AlertTriangle, Send, ShieldCheck } from 'lucide-react';

export function AlertsPanel({ onNavigateToLiaison }: { onNavigateToLiaison?: () => void }) {
  const { alerts } = useSelector((state: RootState) => state.disaster);

  const getSeverityStyles = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-950/40 border-red-500/30 text-red-400';
      case 'high':
        return 'bg-red-900/20 border-red-500/20 text-red-500';
      case 'moderate':
        return 'bg-orange-500/10 border-orange-500/20 text-orange-400';
      case 'low':
      default:
        return 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400';
    }
  };

  return (
    <div className="eoc-card rounded-xl border border-slate-800/80 p-4 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3 border-b border-slate-800 pb-2">
        <AlertTriangle className="w-5 h-5 text-cyan-400" />
        <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-200">
          Community Alerts Panel
        </h3>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {alerts.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-xs italic">
            No active flood predictions or watershed alerts.
          </div>
        ) : (
          alerts.map((alert) => {
            const isSevere = alert.severity === 'high' || alert.severity === 'critical';
            return (
              <div
                key={alert.id}
                className={`p-3 rounded-lg border flex flex-col gap-2 transition-all ${getSeverityStyles(alert.severity)}`}
              >
                {/* Header info */}
                <div className="flex justify-between items-start">
                  <div>
                    <span className="text-[10px] font-bold tracking-wider uppercase opacity-80 block">
                      {alert.district} District
                    </span>
                    <span className="font-display font-bold text-sm tracking-tight">
                      Severity: {alert.severity.toUpperCase()}
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-slate-400">
                    {alert.created_at ? new Date(alert.created_at).toLocaleTimeString() : 'N/A'}
                  </span>
                </div>

                {/* Watershed statistics */}
                <div className="grid grid-cols-2 gap-2 bg-slate-950/30 p-2 rounded text-[10px] font-mono">
                  <div>
                    <span className="text-slate-500">Discharge Q:</span>{' '}
                    <span className="text-slate-200 font-bold">{alert.discharge_q || '0'} m³/s</span>
                  </div>
                  <div>
                    <span className="text-slate-500">FHI Index:</span>{' '}
                    <span className="text-slate-200 font-bold">{alert.fhi_score?.toFixed(2) || '0.00'}</span>
                  </div>
                </div>

                {/* Affected locations list */}
                <div className="text-[10px]">
                  <span className="text-slate-500 block mb-1">Affected Revenue Circles:</span>
                  <div className="flex flex-wrap gap-1">
                    {alert.affected_circles && alert.affected_circles.length > 0 ? (
                      alert.affected_circles.map((circle, i) => (
                        <span
                          key={i}
                          className="bg-slate-950/60 px-1.5 py-0.5 rounded text-slate-300 font-mono text-[9px] border border-slate-800/40"
                        >
                          {circle}
                        </span>
                      ))
                    ) : (
                      <span className="text-slate-500 italic">None reported</span>
                    )}
                  </div>
                </div>

                <div className="border-t border-slate-800/30 pt-2 mt-1 flex items-center justify-between text-[9px]">
                  <span className="text-slate-500">SMS Broadcast:</span>
                  {isSevere ? (
                    <button 
                      onClick={onNavigateToLiaison}
                      className="flex items-center gap-1 text-cyan-400 font-semibold uppercase tracking-wider hover:text-cyan-300 transition-colors cursor-pointer outline-none"
                    >
                      <Send className="w-3 h-3 animate-pulse" />
                      <span>Twilio Broadcast Complete</span>
                    </button>
                  ) : (
                    <div className="flex items-center gap-1 text-slate-400">
                      <ShieldCheck className="w-3 h-3" />
                      <span>Standby (No Broadcast)</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
