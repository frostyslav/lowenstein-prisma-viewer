import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApi } from "../hooks/useApi";

// Clinical thresholds for highlighting outliers.
// AHI: <5 normal, 5-15 mild, 15-30 moderate, >30 severe.
const AHI_MILD = 5;
const AHI_MODERATE = 15;
const AHI_SEVERE = 30;
// Leak 95th percentile above this is considered a large leak (L/min).
const LEAK_HIGH = 24;
// Minimum recommended nightly usage (hours).
const USAGE_MIN = 4;

function ahiClass(ahi: number | null): string {
  if (ahi === null) return "";
  if (ahi >= AHI_SEVERE) return "text-red-700 font-semibold";
  if (ahi >= AHI_MODERATE) return "text-red-600 font-medium";
  if (ahi >= AHI_MILD) return "text-amber-600 font-medium";
  return "text-green-600";
}

function leakClass(leak: number | null): string {
  if (leak === null) return "";
  return leak >= LEAK_HIGH ? "text-red-600 font-medium" : "";
}

function usageClass(hours: number | null): string {
  if (hours === null) return "";
  return hours < USAGE_MIN ? "text-amber-600 font-medium" : "";
}

interface NightSummary {
  id: number;
  date: string;
  usage_hours: number | null;
  therapy_hours: number | null;
  ahi: number | null;
  ai_central: number | null;
  hi_central: number | null;
  leak_95: number | null;
  pressure_median: number | null;
  pressure_95: number | null;
  obstructive_apneas: number | null;
  central_apneas: number | null;
  obstructive_hypopneas: number | null;
  central_hypopneas: number | null;
  reras: number | null;
  flow_limitation_pct: number | null;
}

interface NightsResponse {
  total: number;
  nights: NightSummary[];
}

export function Dashboard() {
  const { data, loading, error } = useApi<NightsResponse>("/api/nights?limit=90");

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-600">Error: {error}</p>;
  if (!data || data.nights.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 mb-4">No data yet.</p>
        <Link
          to="/upload"
          className="inline-block bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          Upload CPAP Data
        </Link>
      </div>
    );
  }

  // Reverse for chronological chart order
  const chartData = [...data.nights].reverse();

  return (
    <div className="space-y-8">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Nights" value={data.total.toString()} />
        <StatCard label="Avg AHI (last 30)" value={avgValue(data.nights.slice(0, 30), "ahi")} />
        <StatCard
          label="Avg Usage (last 30)"
          value={`${avgValue(data.nights.slice(0, 30), "usage_hours")}h`}
        />
      </div>

      {/* AHI chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-sm font-medium text-gray-600 mb-3">AHI Trend</h2>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <ReferenceLine
              y={AHI_MILD}
              stroke="#f59e0b"
              strokeDasharray="4 4"
              label={{ value: "mild", fontSize: 10, fill: "#f59e0b", position: "insideTopRight" }}
            />
            <ReferenceLine
              y={AHI_MODERATE}
              stroke="#dc2626"
              strokeDasharray="4 4"
              label={{
                value: "moderate",
                fontSize: 10,
                fill: "#dc2626",
                position: "insideTopRight",
              }}
            />
            <Line
              type="monotone"
              dataKey="ahi"
              stroke="#2563eb"
              strokeWidth={2}
              dot={<AhiDot />}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Pressure chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-sm font-medium text-gray-600 mb-3">Pressure (cmH2O)</h2>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="pressure_median"
              stroke="#16a34a"
              strokeWidth={2}
              dot={false}
              name="Median"
            />
            <Line
              type="monotone"
              dataKey="pressure_95"
              stroke="#dc2626"
              strokeWidth={1.5}
              dot={false}
              name="95th"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Leak chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-sm font-medium text-gray-600 mb-3">Leak 95th (L/min)</h2>
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line type="monotone" dataKey="leak_95" stroke="#9333ea" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Event breakdown stacked area chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-sm font-medium text-gray-600 mb-3">Event Breakdown</h2>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
            <Area
              type="monotone"
              dataKey="obstructive_apneas"
              stackId="1"
              stroke="#dc2626"
              fill="#dc2626"
              fillOpacity={0.7}
              name="OA"
            />
            <Area
              type="monotone"
              dataKey="central_apneas"
              stackId="1"
              stroke="#ea580c"
              fill="#ea580c"
              fillOpacity={0.7}
              name="CA"
            />
            <Area
              type="monotone"
              dataKey="obstructive_hypopneas"
              stackId="1"
              stroke="#f59e0b"
              fill="#f59e0b"
              fillOpacity={0.7}
              name="OH"
            />
            <Area
              type="monotone"
              dataKey="central_hypopneas"
              stackId="1"
              stroke="#eab308"
              fill="#eab308"
              fillOpacity={0.7}
              name="CH"
            />
            <Area
              type="monotone"
              dataKey="reras"
              stackId="1"
              stroke="#8b5cf6"
              fill="#8b5cf6"
              fillOpacity={0.7}
              name="RERA"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Night list */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-4 py-3 border-b border-gray-100">
          <h2 className="text-sm font-medium text-gray-600">Recent Nights</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-4 py-2 text-left">Date</th>
                <th className="px-4 py-2 text-right">Hours</th>
                <th className="px-4 py-2 text-right">AHI</th>
                <th className="px-4 py-2 text-right">AI(c)</th>
                <th className="px-4 py-2 text-right">HI(c)</th>
                <th className="px-4 py-2 text-right">Leak 95</th>
                <th className="px-4 py-2 text-right">Pressure</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.nights.map((n) => (
                <tr key={n.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2">
                    <Link to={`/nights/${n.id}`} className="text-blue-600 hover:underline">
                      {n.date}
                    </Link>
                  </td>
                  <td className={`px-4 py-2 text-right ${usageClass(n.therapy_hours)}`}>
                    {n.therapy_hours ?? "–"}
                  </td>
                  <td className={`px-4 py-2 text-right ${ahiClass(n.ahi)}`}>{n.ahi ?? "–"}</td>
                  <td className="px-4 py-2 text-right">{n.ai_central ?? "–"}</td>
                  <td className="px-4 py-2 text-right">{n.hi_central ?? "–"}</td>
                  <td className={`px-4 py-2 text-right ${leakClass(n.leak_95)}`}>
                    {n.leak_95 ?? "–"}
                  </td>
                  <td className="px-4 py-2 text-right">{n.pressure_median ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

interface DotProps {
  cx?: number;
  cy?: number;
  value?: number;
}

// Render a colored dot only for nights whose AHI crosses a clinical threshold.
function AhiDot({ cx, cy, value }: DotProps) {
  if (cx === undefined || cy === undefined || value === undefined || value < AHI_MILD) {
    return null;
  }
  let color = "#f59e0b";
  if (value >= AHI_SEVERE) color = "#b91c1c";
  else if (value >= AHI_MODERATE) color = "#dc2626";
  return <circle cx={cx} cy={cy} r={4} fill={color} stroke="#fff" strokeWidth={1} />;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-semibold mt-1">{value}</p>
    </div>
  );
}

function avgValue(nights: NightSummary[], key: keyof NightSummary): string {
  const values = nights.map((n) => n[key]).filter((v): v is number => v !== null);
  if (values.length === 0) return "–";
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return avg.toFixed(1);
}
