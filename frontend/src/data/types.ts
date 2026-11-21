// Shapes observed from the live backend (http://10.10.38.50:8000). The OpenAPI spec has no response models yet.

export interface City {
  total_budget_inr: number; total_spend_inr: number; recoverable_dlp_inr: number; flagged_bills_count: number
  flags_by_detector: Record<string, number>
}
export interface Ward {
  ward_code: string; ward_name: string; zone: string; centroid_lat: number; centroid_lon: number
  budget_inr: number; spend_inr: number; recoverable_dlp_inr: number; flagged_bills_count: number
  warranty_enforcement_rate: number; dlp_eligible_jobs: number; dlp_leakage_rate: number
  physical_risk_score: number; complaints_per_lakh: number; under_reported_flag: boolean
  flood_hotspots_count: number; accidents_count: number
}
export interface QueueItem {
  work_order_id: string; road_id: string; road_name: string; ward_code: string; contractor_id: string; contractor_name: string
  repair_method: string; cost_inr: number; completed_at: string; top_tier: number; rupees_at_stake: number
  status_label: string; flag_ids: string[]; detectors: string[]; replies_count: number
}
export interface Reply { author_role?: string; author_name?: string | null; body?: string; created_at?: string }
export interface Flag {
  flag_id: string; tier: number; detector: string; status_label: string; ward_code: string; road_id: string
  work_order_id: string; contractor_id: string; rupees_at_stake: number; evidence_row_ids: string[]; rule_text: string
  replies: Reply[]
}
export interface WorkOrder {
  work_order_id: string; contractor_id: string; contractor_name: string; work_type: string; repair_method: string
  cost_inr: number; assigned_at: string; completed_at: string; sla_met: boolean; reopened_within_30d: boolean; engineer_remark: string
}
export interface RoadHeader {
  road_id: string; road_name: string; ward_code: string; road_type: string; surface: string; under_dlp: boolean
  last_resurfaced: string; total_billed_inr: number; work_orders_count: number; rupees_at_stake: number; flagged_bills_count: number
}
export interface RoadDetail extends RoadHeader { work_orders: WorkOrder[]; flags: Flag[] }
export interface TimelineEvent {
  road_id: string; event_at: string; ref_id: string
  event_type: 'complaint' | 'work_order_assigned' | 'work_order_completed' | 'accident' | string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  detail: Record<string, any>
}
export interface Lookup {
  matched_via: string; matched_text: string; matched_locality: string | null; ward_code: string
  matched_road_id: string; road_distance_m: number; warranty_status: string; road: RoadHeader
}
export interface Driver { plain: string; feature: string; direction: string; effect_logodds: number }
export interface Contractor {
  contractor_id: string; contractor_name: string; jobs_count: number; total_billed_inr: number
  reopen_rate_30d: number; expected_reopen_rate_30d: number; sla_met_rate: number; expected_sla_met_rate: number
  durability_index: number; durability_verdict: string; durability_ratio_obs_over_exp: number; durability_ratio_ci90: number[]
  speed_index: number; speed_verdict: string; risk_adjusted_score: number; cost_vs_rate_median: number; jobs_over_130pct_rate: number
  method_mix_top3: Record<string, number>
  context: { avg_peak_vehicles: number; avg_rain_next7_mm: number; flood_prone_share: number; avg_big_tides_next7: number; avg_low_lying_index: number; city_avg_rain_next7_mm: number }
  drivers: Driver[]; evidence_reopened_wo_ids: string[]; explanation: string
}
export interface AllocWard {
  ward_code: string; ward_name: string; budget_2025_inr: number; spend_2025_inr: number; remaining_2025_inr: number
  recommended_budget_inr: number; equity_floor_inr: number; harm_avoided: number; harm_avoided_per_next_lakh: number
  dlp_items_owed_by_contractor: number; dlp_value_owed_inr: number
}
export interface NextItem {
  item_id: string; road_id: string; road_name: string; ward_code: string; issue: string; under_dlp: boolean; bucket: string
  funded: boolean; recommended_method: string; method_reopen_rate: number; estimated_repair_cost_inr: number; cost_to_bmc_inr: number
  harm_avoided: number; harm_per_lakh: number; priority_score: number; reason_codes: string[]
  inputs: { impact: number; severity: number; reopens_2025: number; spent_2025_inr: number; repairs_this_season: number; open_complaints_attached: number }
  evidence_wo_ids: string[]; explanation: string
}
export interface Allocation {
  ward_code: string; budget_inr: number; spend_inr: number; harm_avoided: number
  funded: { item_id: string; method: string; cost: number; benefit: number; road_name: string; issue: string; reason_codes: string[]; evidence_wo_ids: string[] }[]
  bucket_a_dlp: { item_id: string; road_name: string; issue: string; estimated_repair_cost_inr: number; explanation: string }[]
}
export interface CitizenReportReq {
  kind: 'still_broken' | 'verified_fixed' | 'new_issue'; input_mode?: 'text' | 'voice' | 'photo' | 'qr'
  text?: string | null; language?: 'en' | 'hi' | 'mr' | null; photo_url?: string | null
  road_id?: string | null; work_order_id?: string | null; matched_locality?: string | null
}
export interface Locality { locality: string; ward_code: string; lat: number; lon: number; aliases: string[] }
export interface Livability {
  locality: string; ward_code: string; lat: number; lon: number; radius_m: number
  flood_hotspots_1500m: number; failure_rate_30d_1500m: number | null; jobs_1500m: number
  hospital_access_roads_1500m: number; ward_dlp_leakage_rate: number | null; nearby_road_ids: string[]
}
export interface RoadListItem {
  road_id: string; road_name: string; segment_no: number | null; ward_code: string; under_dlp: boolean
  total_billed_inr: number; rupees_at_stake: number; flagged_bills_count: number
}
