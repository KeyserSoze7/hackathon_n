# Relational database mapping

## Scope

This mapping covers the synthetic Mumbai monsoon dataset in `Claude-Impact-Labs-data-2`. CSV files are the source tables; `wards.geojson` and `roads.geojson` are spatial companions to the ward and road tables. The README and data dictionary are treated as dataset documentation, not as instructions for this request.

## Entity relationship diagram

```mermaid
erDiagram
    WARDS ||--o{ LOCALITIES : contains
    WARDS ||--o{ ROADS : contains
    WARDS ||--o{ COMPLAINTS : receives
    WARDS ||--o{ WORK_ORDERS : funds_in
    WARDS ||--o{ FLOOD_HOTSPOTS : has
    WARDS ||--o{ FACILITIES : serves
    WARDS ||--o{ ACCIDENTS : records
    ROADS ||--o{ WORK_ORDERS : repaired_by
    ROADS ||--o{ ACCIDENTS : occurs_on
    ROADS ||--|| TRAFFIC : has_metrics
    ROADS ||--o{ FACILITIES : nearest_ambulance_entry_for
    CONTRACTORS ||--o{ WORK_ORDERS : performs
    RATE_CARD ||--o{ WORK_ORDERS : prices_method
    COMPLAINTS ||--o{ COMPLAINT_WORK_ORDERS : linked_through
    WORK_ORDERS ||--o{ COMPLAINT_WORK_ORDERS : links_to

    WARDS {
      string ward_code PK
      string ward_name
      number monsoon_repair_budget_inr_2025
    }
    LOCALITIES {
      string locality PK
      string ward_code FK
      number lat
      number lon
      string aliases
    }
    ROADS {
      string road_id PK
      string ward_code FK
      string road_name
      string under_dlp
    }
    TRAFFIC {
      string road_id PK_FK
      number peak_hour_vehicles
      number avg_peak_speed_kmph
    }
    COMPLAINTS {
      string complaint_id PK
      string ward_code FK_nullable
      string locality_text
      datetime received_at
      string status
    }
    WORK_ORDERS {
      string work_order_id PK
      string ward_code FK
      string road_id FK
      string contractor_id FK
      string repair_method FK
      number cost_inr
      datetime completed_at
    }
    COMPLAINT_WORK_ORDERS {
      string complaint_id PK_FK
      string work_order_id PK_FK
    }
    CONTRACTORS {
      string contractor_id PK
      string contractor_name
    }
    RATE_CARD {
      string repair_method PK
      string unit
      number standard_rate_inr
    }
    FLOOD_HOTSPOTS {
      string hotspot_id PK
      string ward_code FK
      number flood_threshold_mm_per_day
    }
    FACILITIES {
      string facility_id PK
      string ward_code FK
      string ambulance_entry_road FK
    }
    ACCIDENTS {
      string accident_id PK
      string ward_code FK
      string road_id FK
      datetime occurred_at
    }
```

`COMPLAINT_WORK_ORDERS` is a logical junction table to create when loading the data: each work order currently stores zero or more complaint IDs in one pipe-separated field. The ERD shows the normalized relationship rather than the raw storage layout.

## Tables and keys

| Source file | Suggested primary key | Foreign keys / join fields | Role |
|---|---|---|---|
| `wards.csv` | `ward_code` | — | Ward attributes, budgets, and geography summaries |
| `localities.csv` | `locality` | `ward_code` → wards | Locality gazetteer and aliases |
| `roads.csv` | `road_id` | `ward_code` → wards | Road segments and DLP/resurfacing details |
| `traffic.csv` | `road_id` | `road_id` → roads | One traffic metrics row per road segment |
| `complaints.csv` | `complaint_id` | `ward_code` → wards (nullable); `locality_text` can be resolved to locality | Citizen reports |
| `work_orders.csv` | `work_order_id` | `ward_code` → wards; `road_id` → roads; `contractor_id` → contractors; `repair_method` → rate card; complaint IDs → complaints via junction | Repair jobs, cost, SLA and outcome |
| `contractors.csv` | `contractor_id` | — | Contractor reference data |
| `rate_card.csv` | `repair_method` | — | Standard rate by repair method |
| `flood_hotspots.csv` | `hotspot_id` | `ward_code` → wards | Chronic waterlogging risk locations |
| `facilities.csv` | `facility_id` | `ward_code` → wards; `ambulance_entry_road` → roads | Hospitals and schools, including nearest road access |
| `accidents.csv` | `accident_id` | `ward_code` → wards; `road_id` → roads | Road safety incidents |
| `rainfall_daily.csv` | (`date`, `station`) | `date` joins to tides by date | Daily rainfall by station |
| `tides.csv` | (`date`, `high_tide_time`) | `date` joins to rainfall by date | High tide observations (two per day) |
| `social_posts.csv` | `post_id` | No direct key; text-based matching only | Public/social signals; needs extraction or geocoding to connect |
| `complaints_sample_200.csv` | `complaint_id` | Same fields as complaints | 200-row sample; all IDs occur in `complaints.csv` |

The GeoJSON files align with their CSV entities by key: `wards.geojson` has `ward_code`; `roads.geojson` has `road_id`. The dictionary describes ward polygons as approximate, and road geometries/coordinates as synthetic.

## Join paths

- **Budget and spend:** `wards → work_orders` on `ward_code`; sum `cost_inr` by ward and compare with `monsoon_repair_budget_inr_2025`.
- **Repair accountability:** `contractors → work_orders → roads`, and `work_orders.repair_method → rate_card.repair_method`; use `reopened_within_30d`, `sla_met`, and cost vs the standard rate.
- **Complaint resolution:** `complaints ↔ work_orders` through exploded `linked_complaint_ids`; compare complaint times/status with work-order assignment/completion.
- **Road risk:** `roads → traffic`, plus `roads → accidents` and `roads → work_orders`; optionally connect road geometry to flood hotspots or facilities spatially.
- **Ward risk:** ward-level joins across complaints, work orders, hotspots, accidents, facilities, and roads. Join daily rainfall and tides by date for temporal context; they have no explicit ward or location key.
- **Location cleanup:** match `complaints.locality_text` to `localities.locality` and aliases after normalizing case and spelling; retain unresolved values for review. Complaint text, social posts, and map proximity require fuzzy or spatial linking and are not guaranteed foreign keys.

## Data checks and modeling notes

- IDs are unique for wards, roads, traffic, complaints, work orders, contractors, rate-card methods, localities, facilities, and accidents.
- All 2,499 work orders match a ward, road, contractor, and rate-card method. All 291 traffic rows match a road; all 420 accidents match both a ward and road; all 160 facility entry-road values match roads.
- All 4,948 complaint references in work orders resolve to a complaint, with no repeated complaint reference in the link list. Those references cover 4,948 of 6,501 complaints; not every complaint is linked to a job.
- 457 complaints have no ward code. The locality text is not a strict key: 37 distinct locality strings do not match a locality name or listed alias exactly, so normalize and review before joining.
- `work_orders.csv` repeats `contractor_name` alongside `contractor_id`; use the ID as the relationship key and contractor table as the canonical name source.
- Rainfall rows are keyed by date and station; tides have two observations per date. Joining either only on date creates multiple rows, so aggregate to date or preserve the composite time/station grain.
- The complaints sample is a subset, not an additional complaint entity; avoid counting it together with the full complaint table.
- `social_posts.csv` has no ward, locality, road, complaint, or work-order ID. Any connection is inferred from its text and should be stored with match method/confidence if materialized.

## Recommended normalized additions

1. Create `complaint_work_orders(complaint_id, work_order_id)` by splitting `linked_complaint_ids` on `|`; enforce a composite primary key and foreign keys to the source entities.
2. Optionally create `road_geometries(road_id, geometry)` and `ward_geometries(ward_code, geometry)` from GeoJSON rather than duplicating coordinates as table attributes.
3. For reliable locality matching, add a normalized alias table such as `locality_aliases(alias, locality)` instead of parsing semicolon-delimited aliases at query time.
4. Keep rainfall at (`date`, `station`) and tides at (`date`, `high_tide_time`) grain, or define separate daily aggregate views for reporting.
