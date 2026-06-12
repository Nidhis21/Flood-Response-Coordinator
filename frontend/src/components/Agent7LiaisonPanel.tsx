import { useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import type { RootState } from '../store';
import { addSmsInboundSimulated, addSmsSent } from '../store/slices/disasterSlice';
import type { SmsMessage } from '../store/slices/disasterSlice';
import { MessageSquare, Send, Smartphone, ShieldCheck } from 'lucide-react';

// Sample simulation template payloads
const SMS_TEMPLATES = [
  { label: 'SOS Rescue', body: '27.235,94.105,5,Water surrounding our house, trapped on second floor' },
  { label: 'SOS Medical', body: '27.228,94.098,2,Elderly woman fell in water, shivering and chest pains' },
  { label: 'Shelter Request', body: 'Is the Gogamukh community hall open? Need shelter for 4 people.' },
  { label: 'Supply Request', body: 'Food and fresh water running out at Lakhimpur town block.' },
  { label: 'Blockage Report', body: 'Huge floating tree trunk blocking road under Naoboicha bridge.' },
  { label: 'Water Level', body: 'Water has risen 1 meter past danger marker in past 30 minutes.' },
];

export function Agent7LiaisonPanel() {
  const dispatch = useDispatch();
  const { smsLogs, sosQueue } = useSelector((state: RootState) => state.disaster);

  // Inbound simulation state
  const [inboundPhone, setInboundPhone] = useState('+919876543210');
  const [inboundBody, setInboundBody] = useState('');
  const [simulating, setSimulating] = useState(false);

  // Outbound console state
  const [outboundPhone, setOutboundPhone] = useState('');
  const [outboundBody, setOutboundBody] = useState('');

  // Classify message helper (client side visual helper for mock classification)
  const classifyMessage = (body: string): { classification: SmsMessage['classification']; confidence: number } => {
    const text = body.toLowerCase();
    
    // GPS based or rescue text
    if (/^\d{2}\.\d+,\s*\d{2}\.\d+/.test(text) || text.includes('trap') || text.includes('roof') || text.includes('save') || text.includes('rescue')) {
      if (text.includes('chest') || text.includes('pain') || text.includes('hurt') || text.includes('injur') || text.includes('bleed') || text.includes('shiver') || text.includes('sick')) {
        return { classification: 'SOS Medical', confidence: 0.98 };
      }
      return { classification: 'SOS Rescue', confidence: 0.95 };
    }

    if (text.includes('shelter') || text.includes('hall') || text.includes('school') || text.includes('stay') || text.includes('evac')) {
      return { classification: 'Shelter Request', confidence: 0.92 };
    }

    if (text.includes('food') || text.includes('water') || text.includes('medicine') || text.includes('ration') || text.includes('supply')) {
      return { classification: 'Supply Request', confidence: 0.89 };
    }

    if (text.includes('block') || text.includes('bridge') || text.includes('road') || text.includes('tree') || text.includes('log')) {
      return { classification: 'Blockage Report', confidence: 0.94 };
    }

    if (text.includes('rise') || text.includes('level') || text.includes('river') || text.includes('meter') || text.includes('water')) {
      return { classification: 'Water Level Report', confidence: 0.91 };
    }

    return { classification: 'General Inquiry', confidence: 0.75 };
  };

  // Submit Inbound SMS Simulator to backend
  const handleSimulateInbound = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inboundBody.trim()) return;

    setSimulating(true);
    try {
      const formData = new FormData();
      formData.append('From', inboundPhone);
      formData.append('Body', inboundBody);

      // Post to FastAPI endpoint
      const res = await fetch('/api/twilio/inbound', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        const { classification, confidence } = classifyMessage(inboundBody);
        
        // Dispatch local SMS Log copy
        dispatch(addSmsInboundSimulated({
          id: `in-${Date.now()}`,
          phone: inboundPhone,
          body: inboundBody,
          direction: 'inbound',
          timestamp: new Date().toISOString(),
          classification,
          confidence,
          status: 'processed',
          sos_id: data.sos_id,
        }));

        setInboundBody('');
      } else {
        console.error('Failed to post SMS to Twilio backend endpoint.');
      }
    } catch (err) {
      console.error('Error simulating SMS:', err);
    } finally {
      setSimulating(false);
    }
  };

  // Quick select simulation template
  const handleSelectTemplate = (body: string) => {
    setInboundBody(body);
  };

  // Compose outbound SMS and send
  const handleSendOutbound = (e: React.FormEvent) => {
    e.preventDefault();
    if (!outboundPhone.trim() || !outboundBody.trim()) return;

    // Dispatch to local log
    dispatch(addSmsSent({
      phone: outboundPhone,
      message: outboundBody,
    }));

    setOutboundBody('');
    alert(`SMS sent to ${outboundPhone} via simulated Twilio dispatch.`);
  };

  // Set recipient phone number quickly from queue
  const handleSelectSurvivorPhone = (phone: string) => {
    setOutboundPhone(phone);
  };

  // Apply templates to response message body
  const applyResponseTemplate = (type: string) => {
    switch (type) {
      case 'dispatch':
        setOutboundBody('EOC UPDATE: Rescue dispatched. Boat B1 is en route. ETA is 15 minutes. Stay on high ground.');
        break;
      case 'eta':
        setOutboundBody('EOC UPDATE: Rescue team has departed. Current ETA is ~10 minutes. Flash lights or sound whistles on arrival.');
        break;
      case 'shelter':
        setOutboundBody('EOC UPDATE: Gogamukh Community Hall has available capacity. Proceed along High Street North, water level low.');
        break;
      case 'alert':
        setOutboundBody('CRITICAL: Flood levels rising on Ranganadi River. Severe warning for Laluk/Naoboicha circles. Move to upper levels immediately.');
        break;
      case 'status':
        setOutboundBody('EOC UPDATE: Your rescue request is queued. Dispatch teams are active in your area. Hang tight.');
        break;
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full overflow-hidden text-slate-200">
      
      {/* 1. SMS SIMULATOR (Left) */}
      <div className="eoc-card rounded-xl border border-slate-800 p-4 flex flex-col h-full overflow-hidden">
        <div className="flex items-center gap-2 mb-3 border-b border-slate-800 pb-2">
          <Smartphone className="w-5 h-5 text-cyan-400" />
          <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-100">
            SMS Simulator (Inbound)
          </h3>
        </div>

        <form onSubmit={handleSimulateInbound} className="space-y-4 flex-1 overflow-y-auto pr-1">
          <div>
            <label className="text-[10px] font-mono text-slate-400 block mb-1">
              SURVIVOR PHONE NUMBER (SENDER)
            </label>
            <input
              type="text"
              className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-cyan-400 focus:outline-none focus:border-cyan-500"
              value={inboundPhone}
              onChange={(e) => setInboundPhone(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="text-[10px] font-mono text-slate-400 block mb-1">
              MESSAGE BODY (SMS CONTENT)
            </label>
            <textarea
              className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-sans h-24 focus:outline-none focus:border-cyan-500 placeholder-slate-600"
              value={inboundBody}
              onChange={(e) => setInboundBody(e.target.value)}
              placeholder="Enter latitude,longitude,people_count,details OR free text description..."
              required
            />
          </div>

          <button
            type="submit"
            disabled={simulating}
            className="w-full bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold py-2 rounded text-xs transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            <Send className="w-3.5 h-3.5" />
            {simulating ? 'Processing...' : 'Simulate SMS Inbound'}
          </button>

          {/* Quick-test templates */}
          <div className="pt-3 border-t border-slate-800/40">
            <span className="text-[9px] font-mono text-slate-400 block mb-2">
              CLICK TO LOAD SIMULATION TEMPLATES:
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              {SMS_TEMPLATES.map((tpl) => (
                <button
                  key={tpl.label}
                  type="button"
                  onClick={() => handleSelectTemplate(tpl.body)}
                  className="bg-slate-900 border border-slate-800/80 hover:border-cyan-500/40 hover:bg-slate-800/40 rounded p-1.5 text-[10px] text-left text-slate-300 font-semibold transition-colors"
                >
                  {tpl.label}
                </button>
              ))}
            </div>
          </div>
        </form>
      </div>

      {/* 2. INBOUND SMS CLASSIFICATION LOG (Center) */}
      <div className="eoc-card rounded-xl border border-slate-800 p-4 flex flex-col h-full overflow-hidden">
        <div className="flex items-center gap-2 mb-3 border-b border-slate-800 pb-2">
          <MessageSquare className="w-5 h-5 text-cyan-400" />
          <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-100">
            Inbound Classifier Log
          </h3>
        </div>

        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {smsLogs.filter(m => m.direction === 'inbound').length === 0 ? (
            <div className="text-center py-8 text-slate-500 text-xs italic">
              No inbound SMS logs processed yet. Use simulator to test.
            </div>
          ) : (
            smsLogs
              .filter((m) => m.direction === 'inbound')
              .map((msg) => (
                <div key={msg.id} className="p-3 bg-slate-950/40 rounded-lg border border-slate-900 flex flex-col gap-2">
                  <div className="flex justify-between items-start">
                    <span
                      onClick={() => handleSelectSurvivorPhone(msg.phone)}
                      className="text-[10px] font-mono text-cyan-400 font-semibold cursor-pointer hover:underline"
                    >
                      {msg.phone}
                    </span>
                    <span className="text-[8px] font-mono text-slate-500">
                      {new Date(msg.timestamp).toLocaleTimeString()}
                    </span>
                  </div>

                  {/* Classification tag */}
                  <div className="flex justify-between items-center text-[9px] bg-slate-950/80 p-1 px-1.5 rounded border border-slate-800/50">
                    <span className="text-slate-400 font-mono">Category:</span>
                    <span className="font-bold text-cyan-300 font-display uppercase tracking-wider">
                      {msg.classification || 'SOS Request'}
                    </span>
                    <span className="text-slate-500">|</span>
                    <span className="text-slate-400 font-mono">Conf:</span>
                    <span className="font-bold font-mono text-emerald-400">
                      {Math.round((msg.confidence || 0.95) * 100)}%
                    </span>
                  </div>

                  <p className="text-xs text-slate-300 italic font-mono bg-slate-950/20 p-2 rounded leading-relaxed border border-slate-900/30">
                    "{msg.body}"
                  </p>

                  {/* SOS ID link if parsed */}
                  {msg.sos_id && (
                    <div className="text-[8px] font-mono text-slate-500 flex justify-between">
                      <span>Created Event: SOS #{msg.sos_id}</span>
                      <span className="text-emerald-400 flex items-center gap-0.5">
                        <ShieldCheck className="w-2.5 h-2.5" /> Parsed & Queued
                      </span>
                    </div>
                  )}
                </div>
              ))
          )}
        </div>
      </div>

      {/* 3. SMS RESPONSE CENTER (Right) */}
      <div className="eoc-card rounded-xl border border-slate-800 p-4 flex flex-col h-full overflow-hidden">
        <div className="flex items-center gap-2 mb-3 border-b border-slate-800 pb-2">
          <Send className="w-5 h-5 text-cyan-400" />
          <h3 className="font-display font-bold text-sm uppercase tracking-wider text-slate-100">
            SMS Response Center
          </h3>
        </div>

        <form onSubmit={handleSendOutbound} className="space-y-4 flex-1 overflow-y-auto pr-1">
          <div>
            <label className="text-[10px] font-mono text-slate-400 block mb-1">
              RECIPIENT SURVIVOR PHONE
            </label>
            <input
              type="text"
              className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-cyan-400 focus:outline-none focus:border-cyan-500 placeholder-slate-600"
              value={outboundPhone}
              onChange={(e) => setOutboundPhone(e.target.value)}
              placeholder="e.g. +919876543210"
              required
            />

            {/* Quick list of active SOS phones */}
            {sosQueue.filter((s) => s.status !== 'rescued').length > 0 && (
              <div className="mt-2">
                <span className="text-[8px] font-mono text-slate-500 block mb-1">
                  ACTIVE SURVIVORS CALLING FOR HELP:
                </span>
                <div className="flex flex-wrap gap-1 max-h-16 overflow-y-auto">
                  {sosQueue
                    .filter((s) => s.status !== 'rescued')
                    .map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => handleSelectSurvivorPhone(s.phone)}
                        className="bg-slate-950 border border-slate-800 hover:border-cyan-500/40 rounded px-1.5 py-0.5 text-[9px] font-mono text-slate-300"
                      >
                        SOS #{s.id} ({s.phone.slice(-4)})
                      </button>
                    ))}
                </div>
              </div>
            )}
          </div>

          <div>
            <label className="text-[10px] font-mono text-slate-400 block mb-1">
              OUTBOUND SMS TEXT BODY
            </label>
            <textarea
              className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-sans h-24 focus:outline-none focus:border-cyan-500"
              value={outboundBody}
              onChange={(e) => setOutboundBody(e.target.value)}
              placeholder="Write response message..."
              required
            />
          </div>

          {/* Quick response templates buttons */}
          <div>
            <span className="text-[9px] font-mono text-slate-400 block mb-1.5">
              RESPONSE TEMPLATES:
            </span>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => applyResponseTemplate('dispatch')}
                className="bg-slate-900 hover:bg-slate-800 px-2 py-1 rounded text-[9px] border border-slate-800 font-semibold"
              >
                Dispatch Conf
              </button>
              <button
                type="button"
                onClick={() => applyResponseTemplate('eta')}
                className="bg-slate-900 hover:bg-slate-800 px-2 py-1 rounded text-[9px] border border-slate-800 font-semibold"
              >
                Rescue ETA
              </button>
              <button
                type="button"
                onClick={() => applyResponseTemplate('shelter')}
                className="bg-slate-900 hover:bg-slate-800 px-2 py-1 rounded text-[9px] border border-slate-800 font-semibold"
              >
                Shelter Directions
              </button>
              <button
                type="button"
                onClick={() => applyResponseTemplate('alert')}
                className="bg-slate-900 hover:bg-slate-800 px-2 py-1 rounded text-[9px] border border-slate-800 font-semibold"
              >
                Alert Notice
              </button>
              <button
                type="button"
                onClick={() => applyResponseTemplate('status')}
                className="bg-slate-900 hover:bg-slate-800 px-2 py-1 rounded text-[9px] border border-slate-800 font-semibold"
              >
                Status Update
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="w-full bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold py-2 rounded text-xs transition-colors flex items-center justify-center gap-1.5"
          >
            <Send className="w-3.5 h-3.5" />
            Send Twilio Response SMS
          </button>
        </form>
      </div>

    </div>
  );
}
