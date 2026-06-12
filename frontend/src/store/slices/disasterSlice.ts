import { createSlice } from '@reduxjs/toolkit';
import type { PayloadAction } from '@reduxjs/toolkit';

export interface Resource {
  id: number;
  type: 'helicopter' | 'boat' | 'truck' | 'medical_team';
  name: string;
  lat: number;
  lng: number;
  status: 'available' | 'dispatched' | 'maintenance';
  inventory: Record<string, number>;
}

export interface Shelter {
  id: number;
  name: string;
  lat: number;
  lng: number;
  capacity: number;
  current_occupancy: number;
  food_stock: number;
  water_stock: number;
  medicine_stock: number;
  status: 'open' | 'full' | 'closed';
}

export interface SOSEvent {
  id: number;
  phone: string;
  lat: number;
  lng: number;
  district?: string;
  people_count: number;
  injury_description?: string;
  triage_level: number; // 1 (critical) - 5 (minor)
  status: 'pending' | 'assigned' | 'rescued';
  assigned_resource_id?: number | null;
  assigned_resource_name?: string;
  eta_minutes?: number;
  created_at: string;
}

export interface FloodAlert {
  id: number;
  district: string;
  severity: 'low' | 'moderate' | 'high' | 'critical';
  discharge_q: number;
  estimated_flood_time?: string | null;
  affected_circles: string[];
  fhi_score: number;
  created_at: string;
}

export interface DecisionLog {
  id: number;
  event_type: string;
  agent_name: string;
  request_a: {
    agent?: string;
    sos_id?: number;
    lives_at_risk?: number;
    time_to_critical_hours?: number;
    irreversibility?: number;
    distance_km?: number;
    reason?: string;
  };
  request_b: {
    agent?: string;
    sos_id?: number;
    lives_at_risk?: number;
    time_to_critical_hours?: number;
    irreversibility?: number;
    distance_km?: number;
    reason?: string;
  };
  score_a?: number;
  score_b?: number;
  winner?: string; // "a" or "b"
  fallback_assigned?: string;
  explanation: string;
  created_at: string;
}

export interface SmsMessage {
  id: string;
  phone: string;
  body: string;
  direction: 'inbound' | 'outbound';
  timestamp: string;
  classification?: 'SOS Rescue' | 'SOS Medical' | 'Shelter Request' | 'Supply Request' | 'Blockage Report' | 'Water Level Report' | 'General Inquiry';
  confidence?: number;
  status?: string; // e.g. "queued", "sent", "delivered", "processed"
  sos_id?: number;
}

export interface ConflictState {
  resource_id: number;
  resource_name: string;
  agent_a: string;
  agent_b: string;
  sos_a_id: number;
  sos_b_id: number;
  timestamp: string;
  resolved: boolean;
}

interface DisasterState {
  resources: Record<number, Resource>;
  shelters: Record<number, Shelter>;
  alerts: FloodAlert[];
  sosQueue: SOSEvent[];
  auditLogs: DecisionLog[];
  smsLogs: SmsMessage[];
  activeConflicts: Record<number, ConflictState>;
  socketConnected: boolean;
  loading: boolean;
  error: string | null;
}

const initialState: DisasterState = {
  resources: {},
  shelters: {},
  alerts: [],
  sosQueue: [],
  auditLogs: [],
  smsLogs: [],
  activeConflicts: {},
  socketConnected: false,
  loading: false,
  error: null,
};

const disasterSlice = createSlice({
  name: 'disaster',
  initialState,
  reducers: {
    setLoading(state, action: PayloadAction<boolean>) {
      state.loading = action.payload;
    },
    setError(state, action: PayloadAction<string | null>) {
      state.error = action.payload;
    },
    setSocketConnected(state, action: PayloadAction<boolean>) {
      state.socketConnected = action.payload;
    },
    // Initial fetch actions
    setResources(state, action: PayloadAction<Resource[]>) {
      action.payload.forEach((res) => {
        state.resources[res.id] = res;
      });
    },
    setShelters(state, action: PayloadAction<Shelter[]>) {
      action.payload.forEach((sh) => {
        state.shelters[sh.id] = sh;
      });
    },
    setAlerts(state, action: PayloadAction<FloodAlert[]>) {
      state.alerts = action.payload;
    },
    setSosQueue(state, action: PayloadAction<SOSEvent[]>) {
      state.sosQueue = action.payload;
    },
    setAuditLogs(state, action: PayloadAction<DecisionLog[]>) {
      state.auditLogs = action.payload;
    },

    // WebSocket / Real-time Updates
    updateFloodAlert(state, action: PayloadAction<Partial<FloodAlert> & { district: string }>) {
      const alert = action.payload;
      const index = state.alerts.findIndex(a => a.district === alert.district);
      const newAlert: FloodAlert = {
        id: alert.id || Date.now(),
        district: alert.district,
        severity: alert.severity || 'low',
        discharge_q: alert.discharge_q || 0,
        estimated_flood_time: alert.estimated_flood_time || null,
        affected_circles: alert.affected_circles || [],
        fhi_score: alert.fhi_score || 0,
        created_at: new Date().toISOString(),
      };
      if (index !== -1) {
        state.alerts[index] = { ...state.alerts[index], ...alert, created_at: new Date().toISOString() };
      } else {
        state.alerts.unshift(newAlert);
      }
    },

    updateResourcePosition(state, action: PayloadAction<{
      resource_id: number;
      name: string;
      old_lat?: number;
      old_lng?: number;
      new_lat: number;
      new_lng: number;
      new_status?: 'available' | 'dispatched' | 'maintenance';
    }>) {
      const { resource_id, new_lat, new_lng, new_status } = action.payload;
      if (state.resources[resource_id]) {
        state.resources[resource_id].lat = new_lat;
        state.resources[resource_id].lng = new_lng;
        if (new_status) {
          state.resources[resource_id].status = new_status;
        }
      }
    },

    addSosEvent(state, action: PayloadAction<SOSEvent>) {
      const sos = action.payload;
      const exists = state.sosQueue.some(e => e.id === sos.id);
      if (!exists) {
        state.sosQueue.unshift(sos);
      } else {
        state.sosQueue = state.sosQueue.map(e => e.id === sos.id ? { ...e, ...sos } : e);
      }
    },

    assignDispatch(state, action: PayloadAction<{
      mission_id: number;
      sos_id: number;
      resource_id: number;
      resource_name: string;
      eta_minutes: number;
    }>) {
      const { sos_id, resource_id, resource_name, eta_minutes } = action.payload;
      state.sosQueue = state.sosQueue.map((sos) => {
        if (sos.id === sos_id) {
          return {
            ...sos,
            status: 'assigned',
            assigned_resource_id: resource_id,
            assigned_resource_name: resource_name,
            eta_minutes,
          };
        }
        return sos;
      });

      // Update resource status to dispatched
      if (state.resources[resource_id]) {
        state.resources[resource_id].status = 'dispatched';
      }
    },

    raiseConflict(state, action: PayloadAction<{
      resource_id: number;
      resource_name: string;
      agent_a: string;
      agent_b: string;
      sos_a_id: number;
      sos_b_id: number;
    }>) {
      const conflict = action.payload;
      state.activeConflicts[conflict.resource_id] = {
        ...conflict,
        timestamp: new Date().toISOString(),
        resolved: false,
      };
    },

    resolveConflict(state, action: PayloadAction<{
      resource_id: number;
      winner: 'a' | 'b';
      score_a: number;
      score_b: number;
      fallback: {
        type: string;
        resource_id?: number;
        resource_name?: string;
        eta_minutes?: number;
        explanation?: string;
      };
      explanation: string;
      audit_log_id?: number;
    }>) {
      const { resource_id, winner, score_a, score_b, fallback, explanation, audit_log_id } = action.payload;

      // Mark the active conflict as resolved
      if (state.activeConflicts[resource_id]) {
        state.activeConflicts[resource_id].resolved = true;
      }

      // Add a decision log entry
      const logEntry: DecisionLog = {
        id: audit_log_id || Date.now(),
        event_type: 'conflict_resolved',
        agent_name: 'conflict_resolution',
        request_a: {
          sos_id: state.activeConflicts[resource_id]?.sos_a_id,
          agent: state.activeConflicts[resource_id]?.agent_a,
        },
        request_b: {
          sos_id: state.activeConflicts[resource_id]?.sos_b_id,
          agent: state.activeConflicts[resource_id]?.agent_b,
        },
        score_a,
        score_b,
        winner,
        fallback_assigned: JSON.stringify(fallback),
        explanation,
        created_at: new Date().toISOString(),
      };
      state.auditLogs.unshift(logEntry);
    },

    updateShelter(state, action: PayloadAction<{
      shelter_id: number;
      name: string;
      current_occupancy: number;
      food_stock: number;
      water_stock: number;
    }>) {
      const { shelter_id, current_occupancy, food_stock, water_stock } = action.payload;
      if (state.shelters[shelter_id]) {
        state.shelters[shelter_id].current_occupancy = current_occupancy;
        state.shelters[shelter_id].food_stock = food_stock;
        state.shelters[shelter_id].water_stock = water_stock;
        
        // Auto update status based on occupancy
        const pct = (current_occupancy / state.shelters[shelter_id].capacity) * 100;
        if (pct >= 100) {
          state.shelters[shelter_id].status = 'full';
        } else if (pct > 0) {
          state.shelters[shelter_id].status = 'open';
        }
      }
    },

    addSmsSent(state, action: PayloadAction<{
      phone: string;
      message: string;
      sos_id?: number;
    }>) {
      const { phone, message, sos_id } = action.payload;
      const newMsg: SmsMessage = {
        id: `out-${Date.now()}`,
        phone,
        body: message,
        direction: 'outbound',
        timestamp: new Date().toISOString(),
        status: 'sent',
        sos_id,
      };
      state.smsLogs.unshift(newMsg);
    },

    addSmsInboundSimulated(state, action: PayloadAction<SmsMessage>) {
      state.smsLogs.unshift(action.payload);
    },
  },
});

export const {
  setLoading,
  setError,
  setSocketConnected,
  setResources,
  setShelters,
  setAlerts,
  setSosQueue,
  setAuditLogs,
  updateFloodAlert,
  updateResourcePosition,
  addSosEvent,
  assignDispatch,
  raiseConflict,
  resolveConflict,
  updateShelter,
  addSmsSent,
  addSmsInboundSimulated,
} = disasterSlice.actions;

export default disasterSlice.reducer;
