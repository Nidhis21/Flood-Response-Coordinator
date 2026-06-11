import { useState } from 'react';
import { useSelector } from 'react-redux';
import type { RootState } from '../store';
import { Search, Filter, ChevronDown, ChevronUp, Scale } from 'lucide-react';

export function DecisionLogPanel() {
  const { auditLogs } = useSelector((state: RootState) => state.disaster);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterWinner, setFilterWinner] = useState('all');
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null);

  // Search & Filter processing
  const filteredLogs = auditLogs.filter((log) => {
    // 1. Search Query Match
    const matchesSearch = 
      log.explanation?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.event_type?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.agent_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (log.request_a?.agent || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (log.request_b?.agent || '').toLowerCase().includes(searchQuery.toLowerCase());

    // 2. Winner Filter Match
    let matchesWinner = true;
    if (filterWinner !== 'all') {
      const winnerAgent = log.winner === 'a' 
        ? log.request_a?.agent 
        : log.request_b?.agent;
      
      matchesWinner = (winnerAgent || '').toLowerCase() === filterWinner.toLowerCase();
    }

    return matchesSearch && matchesWinner;
  });

  const toggleExpandRow = (id: number) => {
    if (expandedLogId === id) {
      setExpandedLogId(null);
    } else {
      setExpandedLogId(id);
    }
  };

  const parseFallback = (fallbackStr: string) => {
    try {
      if (!fallbackStr) return 'None';
      if (fallbackStr.startsWith('{')) {
        const obj = JSON.parse(fallbackStr);
        return `${obj.type === 'alternate_resource' ? 'Alt Resource' : obj.type}: ${obj.resource_name || ''} (ETA: ~${obj.eta_minutes || 0}m) - ${obj.explanation || ''}`;
      }
      return fallbackStr;
    } catch {
      return fallbackStr;
    }
  };

  return (
    <div className="eoc-card rounded-xl border border-slate-800/80 p-5 flex flex-col h-full text-slate-200">
      
      {/* Title */}
      <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <Scale className="w-5.5 h-5.5 text-cyan-400" />
          <div>
            <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-100">
              Conflict Auction Decision Log
            </h3>
            <p className="text-[10px] text-slate-500 font-sans">
              Audit log of autonomous resource auctions and agent priorities
            </p>
          </div>
        </div>
        <span className="text-[10px] font-mono bg-slate-950 px-2 py-0.5 rounded border border-slate-800 text-cyan-400">
          Decisions: {filteredLogs.length}
        </span>
      </div>

      {/* Filter and Search Bar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
          <input
            type="text"
            className="w-full bg-slate-950 border border-slate-800 rounded pl-9 pr-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-cyan-500 placeholder-slate-600"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search decisions, explanations or agent requests..."
          />
        </div>

        {/* Filters */}
        <div className="flex gap-2 justify-end">
          <div className="relative flex items-center bg-slate-950 border border-slate-800 rounded px-2 text-xs text-slate-400">
            <Filter className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
            <select
              className="bg-transparent focus:outline-none text-slate-300 py-1.5"
              value={filterWinner}
              onChange={(e) => setFilterWinner(e.target.value)}
            >
              <option value="all">All Winners</option>
              <option value="rescue">Rescue Agent</option>
              <option value="medical">Medical Agent</option>
              <option value="logistics">Logistics Agent</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Log */}
      <div className="flex-1 overflow-y-auto border border-slate-800/80 rounded-lg">
        <table className="w-full border-collapse text-left text-xs font-sans">
          <thead>
            <tr className="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-mono text-[10px] uppercase tracking-wider">
              <th className="py-2.5 px-3">Timestamp</th>
              <th className="py-2.5 px-3">Resource</th>
              <th className="py-2.5 px-3">Competitors</th>
              <th className="py-2.5 px-3 text-center">Triage Scores</th>
              <th className="py-2.5 px-3">Decision Winner</th>
              <th className="py-2.5 px-3 text-right"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {filteredLogs.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500 italic">
                  No conflict decisions recorded matching filters.
                </td>
              </tr>
            ) : (
              filteredLogs.map((log) => {
                const isExpanded = expandedLogId === log.id;
                
                // Read competitor agents
                const agentA = log.request_a?.agent || 'rescue';
                const agentB = log.request_b?.agent || 'medical';
                
                // Read scores
                const scoreA = log.score_a || 0;
                const scoreB = log.score_b || 0;
                
                // Read winner
                const winnerAgent = log.winner === 'a' ? agentA : agentB;
                
                // Formatting timestamps
                const dateStr = log.created_at 
                  ? new Date(log.created_at).toLocaleTimeString() 
                  : 'N/A';

                return (
                  <>
                    <tr
                      key={log.id}
                      className={`hover:bg-slate-900/40 cursor-pointer ${
                        isExpanded ? 'bg-slate-900/30' : ''
                      }`}
                      onClick={() => toggleExpandRow(log.id)}
                    >
                      <td className="py-3 px-3 font-mono text-slate-400 whitespace-nowrap">
                        {dateStr}
                      </td>
                      <td className="py-3 px-3 font-bold text-slate-200">
                        {log.request_a?.sos_id ? `SOS Contested` : `Supply Contested`}
                      </td>
                      <td className="py-3 px-3">
                        <span className="text-blue-400 font-semibold">{agentA}</span>
                        <span className="text-slate-600 mx-1">vs</span>
                        <span className="text-red-400 font-semibold">{agentB}</span>
                      </td>
                      <td className="py-3 px-3 text-center font-mono font-bold">
                        <span className="text-blue-300">{scoreA.toFixed(2)}</span>
                        <span className="text-slate-600 mx-1">/</span>
                        <span className="text-red-300">{scoreB.toFixed(2)}</span>
                      </td>
                      <td className="py-3 px-3 font-mono">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          winnerAgent === 'medical' 
                            ? 'bg-red-500/15 text-red-400 border border-red-500/20' 
                            : 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/20'
                        }`}>
                          {winnerAgent} Agent
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right">
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4 text-slate-500 inline" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-500 inline" />
                        )}
                      </td>
                    </tr>
                    
                    {/* Expanded Detail Panel */}
                    {isExpanded && (
                      <tr className="bg-slate-950/40 border-l-2 border-cyan-500/80">
                        <td colSpan={6} className="py-4 px-4">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-sans text-slate-300">
                            
                            {/* Competitor detailed metrics comparison */}
                            <div className="bg-slate-900/30 p-3 rounded border border-slate-800 space-y-2">
                              <h4 className="font-semibold text-slate-100 border-b border-slate-800 pb-1 mb-2 font-display uppercase tracking-wider text-[10px]">
                                Weighted Auction Bid Form
                              </h4>
                              
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <div className="font-bold text-blue-400 font-mono uppercase text-[9px] mb-1">
                                    [Bid A] {agentA.toUpperCase()}
                                  </div>
                                  <div className="space-y-0.5 font-mono text-[10px] text-slate-400">
                                    <div>Lives: <span className="text-slate-200">{log.request_a?.lives_at_risk || 0}</span></div>
                                    <div>Critical Time: <span className="text-slate-200">{log.request_a?.time_to_critical_hours || 0}h</span></div>
                                    <div>Distance: <span className="text-slate-200">{log.request_a?.distance_km?.toFixed(2) || 0}km</span></div>
                                    <div>Reason: <span className="text-slate-200 italic font-sans block mt-1">"{log.request_a?.reason || 'stranding rescue'}"</span></div>
                                  </div>
                                </div>
                                
                                <div className="border-l border-slate-800/80 pl-3">
                                  <div className="font-bold text-red-400 font-mono uppercase text-[9px] mb-1">
                                    [Bid B] {agentB.toUpperCase()}
                                  </div>
                                  <div className="space-y-0.5 font-mono text-[10px] text-slate-400">
                                    <div>Lives: <span className="text-slate-200">{log.request_b?.lives_at_risk || 0}</span></div>
                                    <div>Critical Time: <span className="text-slate-200">{log.request_b?.time_to_critical_hours || 0}h</span></div>
                                    <div>Distance: <span className="text-slate-200">{log.request_b?.distance_km?.toFixed(2) || 0}km</span></div>
                                    <div>Reason: <span className="text-slate-200 italic font-sans block mt-1">"{log.request_b?.reason || 'triage airlift'}"</span></div>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Decision Explanation & Fallback Plan */}
                            <div className="space-y-3">
                              <div>
                                <h4 className="font-semibold text-slate-100 mb-1.5 font-display uppercase tracking-wider text-[10px]">
                                  AI Auction Explanation
                                </h4>
                                <p className="bg-slate-900/30 p-2.5 rounded border border-slate-800 text-[11px] leading-relaxed text-slate-300 italic">
                                  "{log.explanation || 'Conflict resolved using priority formula. Winner assigned resource, fallback allocated.'}"
                                </p>
                              </div>

                              <div className="text-[10px] bg-slate-900/30 p-2 rounded border border-slate-800/80">
                                <span className="text-slate-500 font-bold font-mono uppercase block mb-1">
                                  Fallback Plan (For Loser):
                                </span>
                                <span className="text-cyan-400 font-semibold font-mono">
                                  {parseFallback(log.fallback_assigned || '')}
                                </span>
                              </div>
                            </div>

                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
