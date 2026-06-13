import { useEffect, useRef, useCallback } from 'react';
import { useDispatch } from 'react-redux';
import {
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
  updateShelter,
  addSmsSent,
  setSmsLogs,
  setVolunteers,
  setDonations,
  addOrUpdateDonation
} from '../store/slices/disasterSlice';

export function useWebSocket() {
  const dispatch = useDispatch();
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  // 1. Initial State Fetching
  const fetchInitialData = useCallback(async () => {
    try {
      const [resReq, sheltersReq, alertsReq, sosReq, logsReq, smsReq, volReq, donReq] = await Promise.all([
        fetch('/api/resources'),
        fetch('/api/shelters'),
        fetch('/api/alerts'),
        fetch('/api/sos'),
        fetch('/api/audit-log'),
        fetch('/api/sms'),
        fetch('/api/volunteers'),
        fetch('/api/donations')
      ]);

      if (resReq.ok) dispatch(setResources(await resReq.json()));
      if (sheltersReq.ok) dispatch(setShelters(await sheltersReq.json()));
      if (alertsReq.ok) dispatch(setAlerts(await alertsReq.json()));
      if (sosReq.ok) dispatch(setSosQueue(await sosReq.json()));
      if (logsReq.ok) dispatch(setAuditLogs(await logsReq.json()));
      if (smsReq.ok) dispatch(setSmsLogs(await smsReq.json()));
      if (volReq.ok) dispatch(setVolunteers(await volReq.json()));
      if (donReq.ok) dispatch(setDonations(await donReq.json()));
    } catch (err) {
      console.error('Failed to fetch initial disaster data:', err);
    }
  }, [dispatch]);

  // 2. WebSocket connection logic
  const connect = useCallback(() => {
    if (socketRef.current) return;

    // Use window.location to resolve WS URL in a robust way
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // In local development, Vite proxies '/ws' to 'ws://localhost:8000/ws'.
    // If that fails, we can fall back directly to port 8000.
    const wsUrl = import.meta.env.PROD
      ? `${protocol}//${window.location.host}/ws`
      : `ws://localhost:8000/ws`;

    console.log(`Connecting to WebSocket: ${wsUrl}`);
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log('WebSocket connection established.');
      dispatch(setSocketConnected(true));
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { event: eventType, data } = payload;
        console.log(`WebSocket event received: ${eventType}`, data);

        switch (eventType) {
          case 'flood_alert':
            dispatch(updateFloodAlert(data));
            break;
          case 'resource_moved':
            dispatch(updateResourcePosition(data));
            break;
          case 'sos_created':
            dispatch(addSosEvent({
              id: data.sos_id,
              phone: data.phone,
              lat: data.lat,
              lng: data.lng,
              people_count: data.people_count,
              triage_level: data.triage_level,
              injury_description: data.injury_description,
              status: 'pending',
              created_at: new Date().toISOString()
            }));
            break;
          case 'dispatch_assigned':
            dispatch(assignDispatch(data));
            break;
          case 'conflict_raised':
            dispatch(raiseConflict(data));
            break;
          case 'conflict_resolved':
            dispatch(resolveConflict(data));
            break;
          case 'shelter_updated':
            dispatch(updateShelter(data));
            break;
          case 'sms_sent':
            dispatch(addSmsSent(data));
            break;
          case 'donation_updated':
            dispatch(addOrUpdateDonation(data));
            break;
          default:
            console.warn(`Unknown WebSocket event type: ${eventType}`);
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    socket.onclose = () => {
      console.warn('WebSocket connection lost. Attempting reconnect in 3s...');
      dispatch(setSocketConnected(false));
      socketRef.current = null;
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    };

    socket.onerror = (err) => {
      console.error('WebSocket error occurred:', err);
      socket.close();
    };

    socketRef.current = socket;
  }, [dispatch]);

  useEffect(() => {
    fetchInitialData();
    connect();

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [fetchInitialData, connect]);

  // Return a simulation helper to push fake SMS events directly to the backend API
  const sendSimulatedSms = async (fromPhone: string, textBody: string) => {
    try {
      const formData = new FormData();
      formData.append('From', fromPhone);
      formData.append('Body', textBody);

      const response = await fetch('/api/twilio/inbound', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.error('Failed to simulate inbound SMS:', err);
      throw err;
    }
  };

  return { sendSimulatedSms };
}
