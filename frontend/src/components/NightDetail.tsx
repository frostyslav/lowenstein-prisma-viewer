import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../hooks/useApi";
import { SignalViewer } from "./SignalViewer";

interface EventData {
  type: string;
  start_seconds: number;
  duration_seconds: number;
  strength: number | null;
  session_index: number;
}

interface NightDetailData {
  id: number;
  date: string;
  usage_hours: number | null;
  therapy_hours: number | null;
  ahi: number | null;
  ai_central: number | null;
  hi_central: number | null;
  rera_index: number | null;
  obstructive_apneas: number | null;
  central_apneas: number | null;
  obstructive_hypopneas: number | null;
  central_hypopneas: number | null;
  reras: number | null;
  deep_sleep_pct: number | null;
  snore_pct: number | null;
  flow_limitation_pct: number | null;
  leak_95: number | null;
  pressure_median: number | null;
  pressure_95: number | null;
  pressure_max: number | null;
  pressure_min: number | null;
  events: EventData[];
  raw_stats: { stat_id: number; value: string }[];
}

const EVENT_COLORS: Record<string, string> = {
  OA: "#dc2626",
  CA: "#ea580c",
  OH: "#f59e0b",
  CH: "#eab308",
  RERA: "#8b5cf6",
  Snore: "#6b7280",
  FL: "#06b6d4",
  CL: "#ef4444",
};

// biome-ignore lint/complexity/noExcessiveCognitiveComplexity: chart-heavy component
export function NightDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, loading, error } = useApi<NightDetailData>(`/api/nights/${id}`);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;
  if (!data) return <p className="text-gray-500">Not found</p>;

  // Aggregate events by type for the bar chart
  const eventCounts: Record<string, number> = {};
  for (const e of data.events) {
    eventCounts[e.type] = (eventCounts[e.type] || 0) + 1;
  }
  const barData = Object.entries(eventCounts)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/" className="text-blue-600 hover:underline text-sm">
          &larr; Dashboard
        </Link>
        <h2 className="text-lg font-semibold">{data.date}</h2>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <Metric label="Therapy" value={data.therapy_hours ? `${data.therapy_hours}h` : "–"} />
        <Metric label="AHI" value={data.ahi?.toString() ?? "–"} />
        <Metric label="AI (central)" value={data.ai_central?.toString() ?? "–"} />
        <Metric label="HI (central)" value={data.hi_central?.toString() ?? "–"} />
        <Metric label="RERA/h" value={data.rera_index?.toString() ?? "–"} />
        <Metric label="Leak 95" value={data.leak_95 ? `${data.leak_95} L/min` : "–"} />
        <Metric
          label="Pressure Med"
          value={data.pressure_median ? `${data.pressure_median}` : "–"}
        />
        <Metric label="Pressure 95th" value={data.pressure_95 ? `${data.pressure_95}` : "–"} />
        <Metric
          label="Deep Sleep"
          value={data.deep_sleep_pct != null ? `${data.deep_sleep_pct}%` : "–"}
        />
        <Metric label="Snore" value={data.snore_pct != null ? `${data.snore_pct}%` : "–"} />
        <Metric
          label="Flow Lim"
          value={data.flow_limitation_pct != null ? `${data.flow_limitation_pct}%` : "–"}
        />
        <Metric
          label="OA / CA"
          value={`${data.obstructive_apneas ?? 0} / ${data.central_apneas ?? 0}`}
        />
      </div>

      {/* Event counts bar chart */}
      {barData.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-600 mb-3">Event Breakdown</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={barData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="type" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#3b82f6" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Event timeline */}
      {data.events.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-600 mb-3">
            Event Timeline ({data.events.length} events)
          </h3>
          <div className="relative h-16 bg-gray-100 rounded overflow-hidden">
            {data.events.map((e, i) => {
              const totalSeconds = (data.therapy_hours ?? 8) * 3600;
              const left = (e.start_seconds / totalSeconds) * 100;
              const width = Math.max((e.duration_seconds / totalSeconds) * 100, 0.3);
              const color = EVENT_COLORS[e.type] || "#6b7280";
              return (
                <div
                  key={`${e.start_seconds}-${e.type}-${i}`}
                  className="absolute top-0 h-full opacity-70 hover:opacity-100"
                  style={{
                    left: `${left}%`,
                    width: `${width}%`,
                    backgroundColor: color,
                  }}
                  title={`${e.type}: ${e.duration_seconds.toFixed(1)}s at ${formatTime(e.start_seconds)}`}
                />
              );
            })}
          </div>
          <div className="flex gap-3 mt-2 flex-wrap">
            {Object.entries(EVENT_COLORS).map(([type, color]) =>
              eventCounts[type] ? (
                <span key={type} className="flex items-center gap-1 text-xs">
                  <span
                    className="inline-block w-3 h-3 rounded"
                    style={{ backgroundColor: color }}
                  />
                  {type} ({eventCounts[type]})
                </span>
              ) : null,
            )}
          </div>
        </div>
      )}

      {/* Signal waveforms */}
      <SignalViewer nightId={data.id} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded border border-gray-200 px-3 py-2">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h${m.toString().padStart(2, "0")}m`;
}
