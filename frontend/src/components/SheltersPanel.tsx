import { useState } from 'react';
import { useSelector } from 'react-redux';
import type { RootState } from '../store';
import { Home, AlertCircle, PlusCircle } from 'lucide-react';

export function SheltersPanel() {
  const { shelters } = useSelector((state: RootState) => state.disaster);
  const [isAdding, setIsAdding] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    address: '',
    capacity: 100,
    current_occupancy: 0,
    lat: 27.25,
    lng: 94.10
  });

  const handleAddShelter = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/shelters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        setIsAdding(false);
        setFormData({ name: '', address: '', capacity: 100, current_occupancy: 0, lat: 27.25, lng: 94.10 });
      } else {
        console.error("Failed to add shelter");
      }
    } catch (err) {
      console.error(err);
    }
  };

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
        <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-200 flex-1">
          Shelter Status Panel
        </h3>
        <button 
          onClick={() => setIsAdding(!isAdding)}
          className="text-cyan-400 hover:text-cyan-300 transition-colors"
          title="Add New Shelter"
        >
          <PlusCircle className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {isAdding && (
          <form onSubmit={handleAddShelter} className="mb-4 p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex flex-col gap-3 text-xs text-slate-300 shrink-0">
            <div className="flex flex-col gap-1">
              <label className="text-slate-500 text-[10px] uppercase font-bold tracking-wider">Shelter Name</label>
              <input required type="text" placeholder="e.g. Lakhimpur High School" className="bg-slate-950 border border-slate-800 rounded p-1.5" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-slate-500 text-[10px] uppercase font-bold tracking-wider">Address</label>
              <input required type="text" placeholder="e.g. Ward 4, Main Road" className="bg-slate-950 border border-slate-800 rounded p-1.5" value={formData.address} onChange={e => setFormData({...formData, address: e.target.value})} />
            </div>
            <div className="flex gap-2">
              <div className="flex flex-col gap-1 w-1/2">
                <label className="text-slate-500 text-[10px] uppercase font-bold tracking-wider" title="Max number of people it can hold">Total Capacity</label>
                <input required type="number" className="bg-slate-950 border border-slate-800 rounded p-1.5" value={formData.capacity} onChange={e => setFormData({...formData, capacity: parseInt(e.target.value)})} />
              </div>
              <div className="flex flex-col gap-1 w-1/2">
                <label className="text-slate-500 text-[10px] uppercase font-bold tracking-wider" title="Number of people already present">Current Occupancy</label>
                <input required type="number" className="bg-slate-950 border border-slate-800 rounded p-1.5" value={formData.current_occupancy} onChange={e => setFormData({...formData, current_occupancy: parseInt(e.target.value)})} />
              </div>
            </div>
            <div className="flex gap-2">
              <div className="flex flex-col gap-1 w-1/2">
                <label className="text-slate-500 text-[10px] uppercase font-bold tracking-wider">GPS Latitude</label>
                <input required type="number" step="0.0001" className="bg-slate-950 border border-slate-800 rounded p-1.5" value={formData.lat} onChange={e => setFormData({...formData, lat: parseFloat(e.target.value)})} />
              </div>
              <div className="flex flex-col gap-1 w-1/2">
                <label className="text-slate-500 text-[10px] uppercase font-bold tracking-wider">GPS Longitude</label>
                <input required type="number" step="0.0001" className="bg-slate-950 border border-slate-800 rounded p-1.5" value={formData.lng} onChange={e => setFormData({...formData, lng: parseFloat(e.target.value)})} />
              </div>
            </div>
            <button type="submit" className="bg-cyan-900/50 hover:bg-cyan-800 text-cyan-100 py-2 rounded border border-cyan-800/50 mt-1 font-bold w-full">Add Shelter & Broadcast</button>
          </form>
        )}
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
                    {shelter.address && (
                      <span className="text-[10px] text-slate-400 block mb-0.5 truncate max-w-[200px]" title={shelter.address}>
                        {shelter.address}
                      </span>
                    )}
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
