import { useSelector } from 'react-redux';
import type { RootState } from '../store';
import { Truck, Compass, Shield, Users, Battery } from 'lucide-react';

export function ResourceTrackingPanel() {
  const { resources } = useSelector((state: RootState) => state.disaster);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'available':
        return 'text-cyan-400 border-cyan-500/30 bg-cyan-950/20';
      case 'dispatched':
        return 'text-yellow-400 border-yellow-500/30 bg-yellow-950/20';
      case 'maintenance':
      default:
        return 'text-slate-400 border-slate-700 bg-slate-800/40';
    }
  };

  const getResourceIcon = (type: string, color: string) => {
    switch (type) {
      case 'helicopter':
        return <Shield className="w-4 h-4 shrink-0" style={{ color }} />;
      case 'boat':
        return <Compass className="w-4 h-4 shrink-0" style={{ color }} />;
      case 'medical_team':
        return <Users className="w-4 h-4 shrink-0" style={{ color }} />;
      case 'truck':
      default:
        return <Truck className="w-4 h-4 shrink-0" style={{ color }} />;
    }
  };

  return (
    <div className="eoc-card rounded-xl border border-slate-800/80 p-4 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3 border-b border-slate-800 pb-2">
        <Battery className="w-5 h-5 text-cyan-400" />
        <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-200">
          Resource Tracking Panel
        </h3>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {Object.values(resources).length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-xs italic">
            No emergency resources registered.
          </div>
        ) : (
          Object.values(resources).map((resource) => {
            const statusColor = getStatusColor(resource.status);
            const badgeColorHex = 
              resource.status === 'available' ? '#22d3ee' :
              resource.status === 'dispatched' ? '#eab308' : '#94a3b8';

            return (
              <div key={resource.id} className="p-3 bg-slate-900/40 rounded-lg border border-slate-800/60 flex flex-col gap-2">
                {/* Header */}
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    {getResourceIcon(resource.type, badgeColorHex)}
                    <span className="font-display font-bold text-xs text-slate-200">
                      {resource.name}
                    </span>
                    <span className="text-[9px] text-slate-500 capitalize">
                      ({resource.type.replace('_', ' ')})
                    </span>
                  </div>
                  <span className={`text-[8px] font-mono font-bold border rounded px-1.5 py-0.25 uppercase ${statusColor}`}>
                    {resource.status}
                  </span>
                </div>

                {/* Details */}
                <div className="text-[10px] space-y-1 font-mono text-slate-400">
                  <div>GPS: {resource.lat?.toFixed(4)}, {resource.lng?.toFixed(4)}</div>
                  
                  {/* Inventory Summary */}
                  {Object.keys(resource.inventory).length > 0 ? (
                    <div className="pt-1.5 border-t border-slate-800/40 mt-1 flex flex-wrap gap-1">
                      {Object.entries(resource.inventory).map(([item, val]) => (
                        <span
                          key={item}
                          className="bg-slate-950 px-1 py-0.25 rounded text-[8px] border border-slate-900 text-slate-300"
                        >
                          {item.toUpperCase().replace('_', ' ')}: {val}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[9px] italic text-slate-500 border-t border-slate-800/40 pt-1 mt-1">
                      No tools/rations loaded.
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
