import { useSelector, useDispatch } from 'react-redux';
import type { RootState, AppDispatch } from '../store';
import { Package, MapPin, Truck, PhoneCall, CheckCircle, Plus } from 'lucide-react';
import { useState } from 'react';
import { setDonations } from '../store/slices/disasterSlice';

export function DonationsPanel() {
  const { donations } = useSelector((state: RootState) => state.disaster);
  const dispatch = useDispatch<AppDispatch>();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    donor_name: '',
    donor_phone: '',
    donation_type: 'food',
    quantity: 0,
    description: '',
    pickup_lat: 27.23,
    pickup_lng: 94.10,
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'offered':
        return 'text-yellow-400 border-yellow-500/30 bg-yellow-950/20';
      case 'confirmed':
        return 'text-cyan-400 border-cyan-500/30 bg-cyan-950/20';
      case 'collected':
        return 'text-blue-400 border-blue-500/30 bg-blue-950/20';
      case 'delivered':
        return 'text-emerald-400 border-emerald-500/30 bg-emerald-950/20';
      default:
        return 'text-slate-400 border-slate-700 bg-slate-800/40';
    }
  };

  const getDonationIcon = (type: string) => {
    return <Package className="w-5 h-5 text-indigo-400 shrink-0" />;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/donations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        const newDonation = await res.json();
        dispatch(setDonations([newDonation, ...donations]));
        setShowForm(false);
      }
    } catch (e) {
      console.error("Failed to add donation", e);
    }
  };

  return (
    <div className="eoc-card rounded-xl border border-slate-800/80 p-6 flex flex-col h-full bg-slate-900/50">
      <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-3">
          <Package className="w-6 h-6 text-indigo-400" />
          <div>
            <h2 className="font-display font-bold text-lg uppercase tracking-wider text-slate-200">
              Supply Donations
            </h2>
            <p className="text-xs text-slate-400 font-mono">Community Relief Offers & Logistics</p>
          </div>
        </div>
        <button 
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded text-sm font-semibold transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Donation
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-4 p-4 bg-slate-900 border border-slate-700 rounded-lg space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input type="text" placeholder="Donor Name" required className="bg-slate-950 border border-slate-800 p-2 text-sm rounded text-slate-200"
              value={formData.donor_name} onChange={e => setFormData({...formData, donor_name: e.target.value})} />
            <input type="text" placeholder="Phone (e.g. +91...)" required className="bg-slate-950 border border-slate-800 p-2 text-sm rounded text-slate-200"
              value={formData.donor_phone} onChange={e => setFormData({...formData, donor_phone: e.target.value})} />
            <select className="bg-slate-950 border border-slate-800 p-2 text-sm rounded text-slate-200"
              value={formData.donation_type} onChange={e => setFormData({...formData, donation_type: e.target.value})}>
              <option value="food">Food</option>
              <option value="water">Water</option>
              <option value="medicine">Medicine</option>
            </select>
            <input type="number" placeholder="Quantity" required className="bg-slate-950 border border-slate-800 p-2 text-sm rounded text-slate-200"
              value={formData.quantity} onChange={e => setFormData({...formData, quantity: parseInt(e.target.value)})} />
            <input type="text" placeholder="Description" required className="bg-slate-950 border border-slate-800 p-2 text-sm rounded text-slate-200 col-span-2"
              value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} />
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
            <button type="button" onClick={() => setShowForm(false)} className="px-3 py-1 text-sm text-slate-400 hover:text-white transition-colors">Cancel</button>
            <button type="submit" className="px-3 py-1 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-500 font-semibold transition-colors">Save & Auto-Assign Truck</button>
          </div>
        </form>
      )}

      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {donations.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-sm italic">
            No active donation offers in the system.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {donations.map((donation) => (
              <div key={donation.id} className="p-4 bg-slate-950/60 rounded-lg border border-slate-800 flex flex-col gap-3">
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-3">
                    {getDonationIcon(donation.donation_type)}
                    <div>
                      <h3 className="font-bold text-slate-200 capitalize">{donation.donation_type.replace('_', ' ')}</h3>
                      <div className="text-xs font-mono text-slate-400">Qty: <span className="text-indigo-400 font-bold">{donation.quantity}</span></div>
                    </div>
                  </div>
                  <span className={`text-[10px] font-mono font-bold border rounded px-2 py-0.5 uppercase ${getStatusColor(donation.status)}`}>
                    {donation.status}
                  </span>
                </div>

                <p className="text-xs text-slate-300 italic my-1">
                  "{donation.description}"
                </p>
                
                <div className="space-y-2 mt-2 pt-2 border-t border-slate-800/60">
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <CheckCircle className="w-3 h-3" />
                    <span>Donor: <span className="font-bold text-slate-300">{donation.donor_name || 'Anonymous'}</span></span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <PhoneCall className="w-3 h-3" />
                    <span className="font-mono">{donation.donor_phone}</span>
                  </div>
                  {(donation.pickup_lat && donation.pickup_lng) && (
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <MapPin className="w-3 h-3" />
                      <span className="font-mono">Pickup: {donation.pickup_lat.toFixed(4)}, {donation.pickup_lng.toFixed(4)}</span>
                    </div>
                  )}
                  {donation.assigned_truck_id && (
                    <div className="flex items-center gap-2 text-xs text-indigo-300 mt-2 bg-indigo-950/30 p-1.5 rounded border border-indigo-900/50">
                      <Truck className="w-3 h-3 shrink-0" />
                      <span className="font-bold">Assigned to Truck ID: {donation.assigned_truck_id}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
