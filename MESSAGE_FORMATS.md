# MESSAGE_FORMATS.md — Queue Message Schemas

Every inter-agent message in the Flood Response Coordinator flows through one of six `asyncio.Queue` instances defined in `backend/queues.py`. This document specifies the exact JSON format for each queue so all agents produce and consume compatible messages.

> **Convention:** All timestamps are ISO 8601 UTC. All GPS coordinates are decimal degrees. All IDs are integers matching the database primary key.

---

## § alert_queue

**Producer:** Perception Agent  
**Consumer:** Prediction Agent  
**Purpose:** Raw environmental readings from weather APIs or offline mock data.

```json
{
  "river": "Ranganadi",
  "district": "Lakhimpur",
  "station": "Badatighat",
  "timestamp": "2024-06-28T06:00:00Z",
  "rainfall_intensity_mm_per_hr": 42.5,
  "watershed_area_hectares": 134600,
  "runoff_coefficient": 0.233,
  "current_water_level_m": 94.45,
  "danger_level_m": 95.02,
  "latitude": 27.23,
  "longitude": 94.10,
  "source": "open_meteo | mock_rainfall.json"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `river` | string | River name |
| `district` | string | Administrative district |
| `station` | string | Gauging station name |
| `timestamp` | string | ISO 8601 observation time |
| `rainfall_intensity_mm_per_hr` | float | Rainfall intensity (input `I` for rational model) |
| `watershed_area_hectares` | float | Watershed area (input `A` for rational model) |
| `runoff_coefficient` | float | Runoff coefficient 0–1 (input `C` for rational model) |
| `current_water_level_m` | float | Current water level at station |
| `danger_level_m` | float | Official danger level for this station |
| `latitude` | float | Station latitude |
| `longitude` | float | Station longitude |
| `source` | string | Data source identifier |

---

## § sos_queue

**Producer:** Community Liaison Agent (via Twilio webhook in `main.py`)  
**Consumer:** Rescue Agent, Medical Agent  
**Purpose:** Parsed SOS distress calls from flood-affected people.

```json
{
  "sos_id": 1,
  "phone": "+919876543210",
  "lat": 27.2350,
  "lng": 94.1050,
  "people_count": 5,
  "injury_description": "Elderly person with chest pain, 2 children",
  "triage_level": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sos_id` | int | Database ID of the SOS event |
| `phone` | string | Caller's phone number |
| `lat` | float | SOS location latitude |
| `lng` | float | SOS location longitude |
| `people_count` | int | Number of people needing rescue |
| `injury_description` | string | Free-text description of injuries |
| `triage_level` | int | 1 (critical) to 5 (minimal) |

---

## § dispatch_queue

**Producer:** Rescue Agent, Medical Agent  
**Consumer:** Community Liaison Agent  
**Purpose:** Dispatch assignments — tells Liaison to send SMS confirmation to survivor.

```json
{
  "sos_id": 1,
  "mission_id": 1,
  "resource_id": 2,
  "resource_name": "B1",
  "resource_type": "boat",
  "phone": "+919876543210",
  "eta_minutes": 15,
  "shelter_name": "Gogamukh Community Hall",
  "shelter_lat": 27.2700,
  "shelter_lng": 94.1300,
  "message_template": "Help is on the way! {resource_type} {resource_name} arriving in ~{eta_minutes} min. Head to {shelter_name} if able."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sos_id` | int | Which SOS this dispatch addresses |
| `mission_id` | int | Mission record ID |
| `resource_id` | int | Dispatched resource DB ID |
| `resource_name` | string | Human-readable resource name (e.g., "B1") |
| `resource_type` | string | helicopter / boat / truck / medical_team |
| `phone` | string | Survivor's phone number for SMS |
| `eta_minutes` | float | Estimated time of arrival in minutes |
| `shelter_name` | string | Destination shelter name |
| `shelter_lat` | float | Shelter latitude |
| `shelter_lng` | float | Shelter longitude |
| `message_template` | string | SMS template with placeholders |

---

## § resource_update_queue

**Producer:** Logistics Agent  
**Consumer:** Dashboard broadcast, DB updater  
**Purpose:** Resource position or status changes from pre-positioning decisions.

```json
{
  "resource_id": 3,
  "resource_name": "B2",
  "update_type": "position_change",
  "old_lat": 27.2400,
  "old_lng": 94.1120,
  "new_lat": 27.2500,
  "new_lng": 94.0950,
  "new_status": "available",
  "reason": "Pre-positioned closer to predicted flood zone",
  "timestamp": "2024-06-28T07:30:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `resource_id` | int | Resource DB ID |
| `resource_name` | string | Human-readable name |
| `update_type` | string | `position_change` or `status_change` |
| `old_lat` | float | Previous latitude (null if status-only change) |
| `old_lng` | float | Previous longitude (null if status-only change) |
| `new_lat` | float | New latitude |
| `new_lng` | float | New longitude |
| `new_status` | string | available / dispatched / maintenance |
| `reason` | string | Why this change was made |
| `timestamp` | string | ISO 8601 time of update |

---

## § conflict_queue

**Producer:** Rescue Agent, Medical Agent, Logistics Agent  
**Consumer:** Conflict Resolution Agent  
**Purpose:** Two or more agents competing for the same resource simultaneously.

```json
{
  "resource_id": 1,
  "resource_name": "H1",
  "request_a": {
    "agent": "rescue",
    "sos_id": 1,
    "lives_at_risk": 5,
    "time_to_critical_hours": 0.5,
    "irreversibility": 0.7,
    "distance_km": 3.2,
    "reason": "Family stranded on rooftop, water rising"
  },
  "request_b": {
    "agent": "medical",
    "sos_id": 2,
    "lives_at_risk": 1,
    "time_to_critical_hours": 0.25,
    "irreversibility": 0.9,
    "distance_km": 5.1,
    "reason": "Elderly patient with cardiac emergency, needs airlift"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `resource_id` | int | The contested resource |
| `resource_name` | string | Human-readable name |
| `request_a` | object | First agent's request |
| `request_a.agent` | string | Agent name (rescue/medical/logistics) |
| `request_a.sos_id` | int | SOS event this request is for |
| `request_a.lives_at_risk` | int | Number of lives (raw, will be normalized) |
| `request_a.time_to_critical_hours` | float | Hours until situation becomes critical |
| `request_a.irreversibility` | float | 0–1, how irreversible the situation is |
| `request_a.distance_km` | float | Haversine distance from resource to SOS |
| `request_a.reason` | string | Plain English explanation |
| `request_b` | object | Second agent's request (same structure) |

---

## § resolved_queue

**Producer:** Conflict Resolution Agent  
**Consumer:** All other agents (Rescue, Medical, Logistics)  
**Purpose:** Auction result with winner, loser fallback, and explanation.

```json
{
  "resource_id": 1,
  "resource_name": "H1",
  "winner": "b",
  "winning_agent": "medical",
  "winning_sos_id": 2,
  "score_a": 0.62,
  "score_b": 0.78,
  "losing_agent": "rescue",
  "losing_sos_id": 1,
  "fallback": {
    "type": "alternate_resource",
    "resource_id": 2,
    "resource_name": "B1",
    "eta_minutes": 22,
    "explanation": "Boat B1 is 3.2km away and can reach in ~22 minutes"
  },
  "explanation": "The cardiac emergency (SOS #2) scores higher due to extreme irreversibility (0.9) and very short time to critical (15 min). While SOS #1 has more lives at risk (5 vs 1), boat B1 can reach them in 22 minutes as a viable alternative. The helicopter is the only option for the cardiac patient who needs airlift to hospital.",
  "audit_log_id": 7,
  "timestamp": "2024-06-28T08:15:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `resource_id` | int | The contested resource |
| `resource_name` | string | Human-readable name |
| `winner` | string | "a" or "b" |
| `winning_agent` | string | Name of the winning agent |
| `winning_sos_id` | int | SOS event that gets the resource |
| `score_a` | float | Priority score for request A |
| `score_b` | float | Priority score for request B |
| `losing_agent` | string | Name of the losing agent |
| `losing_sos_id` | int | SOS event that doesn't get the resource |
| `fallback` | object | What the loser gets instead |
| `fallback.type` | string | `alternate_resource` / `alternate_shelter` / `wait_time` |
| `explanation` | string | Plain English reasoning for district administrators |
| `audit_log_id` | int | ID of the audit_log record |
| `timestamp` | string | ISO 8601 resolution time |
