import { useSelector } from 'react-redux';
import type { RootState } from '../store';
import { Home, AlertCircle } from 'lucide-react';

export function SheltersPanel() {
  const { shelters } = useSelector((state: RootState) => state.disaster);

  const getOccupancyColor = (pct: number) => {
    if (pct < 70) return 'text-safe-green bg-safe-green';
    if (pct <= 85) return 'text-watch-yellow bg-watch-yellow';
    return 'text-risk-red bg-risk-red';
  };

  const getBarColorClass = (pct: number) => {
    if (pct < 70) return 'bg-safe-green';
    if (pct <= 85) return 'bg-watch-yellow';
    return 'bg-risk-red';
  };

  const isStockLow = (shelter: any) => {
    return shelter.food_stock < 300 || shelter.water_stock < 2000;
  };

  return (
    <div className="eoc-card rounded-xl border border-slate-800/80 p-4 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3 border-b border-slate-800 pb-2">
        <Home className="w-5 h-5 text-cyan-400" />
        <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-200">
          Shelter Status Panel
        </h3>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {Object.values(shelters).length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-xs italic">
            No shelter locations registered.
          </div>
        ) : (
          Object.values(shelters).map((shelter) => {
            const occupancyPct = shelter.capacity > 0 
              ? (shelter.current_occupancy / shelter.capacity) * 100 
              : 0;
            const colorClass = getOccupancyColor(occupancyPct);

            return (
              <div key={shelter.id} className="p-3 bg-slate-900/40 rounded-lg border border-slate-800/60 flex flex-col gap-2.5">
                {/* Shelter Title and Status */}
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-semibold text-xs text-slate-200 block">
                      {shelter.name}
                    </h4>
                    <span className="text-[9px] text-slate-500 font-mono">
                      ID: #{shelter.id} | Status: {shelter.status.toUpperCase()}
                    </span>
                  </div>
                  <span className={`text-[10px] font-bold font-mono px-2 py-0.5 rounded ${colorClass.split(' ')[0]} bg-slate-950/60 border border-slate-800/40`}>
                    {Math.round(occupancyPct)}% Full
                  </span>
                </div>

                {/* Progress bar */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[9px] text-slate-400 font-mono">
                    <span>Occupancy: {shelter.current_occupancy}</span>
                    <span>Cap: {shelter.capacity}</span>
                  </div>
                  <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800/40">
                    <div
                      className={`h-2 rounded-full transition-all duration-500 ${getBarColorClass(occupancyPct)}`}
                      style={{ width: `${Math.min(occupancyPct, 100)}%` }}
                    />
                  </div>
                </div>

                {/* Stocks grid */}
                <div className="grid grid-cols-3 gap-1.5 pt-1 border-t border-slate-800/30 font-mono text-[10px] text-center">
                  <div className="bg-slate-950/40 p-1 rounded border border-slate-800/30">
                    <div className="text-[8px] text-slate-500">FOOD</div>
                    <div className="font-bold text-slate-300">{shelter.food_stock} u</div>
                  </div>
                  <div className="bg-slate-950/40 p-1 rounded border border-slate-800/30">
                    <div className="text-[8px] text-slate-500">WATER</div>
                    <div className="font-bold text-slate-300">{shelter.water_stock} L</div>
                  </div>
                  <div className="bg-slate-950/40 p-1 rounded border border-slate-800/30">
                    <div className="text-[8px] text-slate-500">MEDICINE</div>
                    <div className="font-bold text-slate-300">{shelter.medicine_stock} k</div>
                  </div>
                </div>

                {/* Low Stock Warning */}
                {isStockLow(shelter) && (
                  <div className="flex items-center gap-1.5 text-[9px] text-orange-400 bg-orange-950/20 border border-orange-500/20 p-1.5 rounded">
                    <AlertCircle className="w-3.5 h-3.5 text-orange-400 shrink-0" />
                    <span>Warning: Critical supplies running low. Logistics dispatch recommended.</span>
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
