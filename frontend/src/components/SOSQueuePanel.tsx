import { useSelector } from 'react-redux';
import type { RootState } from '../store';
import { Activity, MapPin, HeartPulse, ShieldAlert, CheckCircle2 } from 'lucide-react';

export function SOSQueuePanel() {
  const { sosQueue } = useSelector((state: RootState) => state.disaster);

  const getTriageBadge = (level: number) => {
    switch (level) {
      case 1:
        return 'bg-red-500/20 text-red-400 border-red-500/30';
      case 2:
        return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
      case 3:
        return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'rescued':
        return 'bg-emerald-500/25 text-emerald-400 border-emerald-500/40';
      case 'assigned':
        return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';
      case 'pending':
      default:
        return 'bg-amber-500/15 text-amber-500 border-amber-500/30 animate-pulse';
    }
  };

  return (
    <div className="eoc-card rounded-xl border border-slate-800/80 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-cyan-400" />
          <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-200">
            Active SOS Queue
          </h3>
        </div>
        <span className="text-[10px] font-mono bg-slate-950 px-2 py-0.5 rounded border border-slate-800 text-cyan-400">
          Total: {sosQueue.filter(s => s.status !== 'rescued').length} Active
        </span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
        {sosQueue.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-xs italic">
            No distress signals in the queue.
          </div>
        ) : (
          sosQueue.map((sos) => {
            // Determine if rescue or medical
            // Medical: if injury info is present or triage involves cardiac/injuries
            const isMedical = 
              sos.injury_description?.toLowerCase().includes('pain') ||
              sos.injury_description?.toLowerCase().includes('sick') ||
              sos.injury_description?.toLowerCase().includes('patient') ||
              sos.injury_description?.toLowerCase().includes('injury') ||
              sos.injury_description?.toLowerCase().includes('medical');

            return (
              <div
                key={sos.id}
                className={`p-3 bg-slate-900/40 rounded-lg border transition-all ${
                  sos.triage_level === 1 && sos.status === 'pending'
                    ? 'border-red-500/50 bg-red-950/5 shadow-[0_0_10px_rgba(239,68,68,0.08)] animate-pulse'
                    : 'border-slate-800/70 hover:border-slate-700/60'
                }`}
              >
                {/* Header */}
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono font-bold text-slate-200">
                      SOS #{sos.id}
                    </span>
                    <span className={`text-[8px] font-mono font-bold border rounded px-1 uppercase ${getTriageBadge(sos.triage_level)}`}>
                      L{sos.triage_level}
                    </span>
                    <span className={`text-[8px] font-mono font-bold border rounded px-1.5 py-0.25 uppercase ${getStatusBadge(sos.status)}`}>
                      {sos.status}
                    </span>
                  </div>
                  
                  {/* Category icon */}
                  <div className="text-[10px] flex items-center gap-1 font-semibold">
                    {isMedical ? (
                      <span className="flex items-center gap-0.5 text-red-400">
                        <HeartPulse className="w-3.5 h-3.5" />
                        Medical
                      </span>
                    ) : (
                      <span className="flex items-center gap-0.5 text-blue-400">
                        <ShieldAlert className="w-3.5 h-3.5" />
                        Rescue
                      </span>
                    )}
                  </div>
                </div>

                {/* Body Details */}
                <div className="space-y-1 text-xs">
                  <div className="flex items-center gap-1 text-slate-400 font-mono text-[10px]">
                    <MapPin className="w-3 h-3 text-slate-500 shrink-0" />
                    <span>Lakhimpur [ {sos.lat?.toFixed(4)}, {sos.lng?.toFixed(4)} ]</span>
                  </div>

                  <div className="flex justify-between text-[10px]">
                    <span><span className="text-slate-500">Phone:</span> <span className="font-mono text-slate-300">{sos.phone}</span></span>
                    <span><span className="text-slate-500">People:</span> <span className="font-bold text-slate-300 font-mono">{sos.people_count}</span></span>
                  </div>

                  <p className="bg-slate-950/60 p-1.5 rounded text-[10px] text-slate-300 border border-slate-900 leading-relaxed italic">
                    "{sos.injury_description || 'Stranded by high flood levels. Immediate rescue required.'}"
                  </p>
                </div>

                {/* Dispatch Details */}
                {sos.status === 'assigned' && (
                  <div className="mt-2.5 border-t border-slate-800/40 pt-2 flex items-center justify-between text-[9px] bg-cyan-950/10 -mx-3 -mb-3 p-2 rounded-b-lg border-x-0 border-b-0">
                    <span className="text-slate-400">Assigned Team:</span>
                    <span className="font-bold text-cyan-400 font-mono">
                      {sos.assigned_resource_name || 'MT1'}
                    </span>
                    <span className="text-slate-500">|</span>
                    <span className="text-slate-400">ETA:</span>
                    <span className="font-bold text-cyan-300 font-mono animate-pulse">
                      ~{sos.eta_minutes ? Math.round(sos.eta_minutes) : '15'} min
                    </span>
                  </div>
                )}

                {sos.status === 'rescued' && (
                  <div className="mt-2.5 border-t border-slate-800/40 pt-2 flex items-center justify-end gap-1.5 text-[9px] bg-emerald-950/10 -mx-3 -mb-3 p-2 rounded-b-lg border-x-0 border-b-0 text-emerald-400 font-semibold uppercase tracking-wider">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Evacuated & Safe</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
