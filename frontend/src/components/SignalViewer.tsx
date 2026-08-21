import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApi } from "../hooks/useApi";

interface ChannelInfo {
  label: string;
  unit: string;
  samples_per_second: number;
  physical_min: number;
  physical_max: number;
}

interface SignalFileInfo {
  id: number;
  session_index: number;
  duration_seconds: number;
  channels: ChannelInfo[];
}

interface SignalFilesResponse {
  night_id: number;
  signal_files: SignalFileInfo[];
}

interface ChannelData {
  values: number[];
  sample_count: number;
}

interface SignalDataResponse {
  start_seconds: number;
  duration_seconds: number;
  channels: Record<string, ChannelData>;
}

const CHANNEL_COLORS: Record<string, string> = {
  RespFlow: "#2563eb",
  Pressure: "#16a34a",
  LeakFlowBreath: "#9333ea",
  FlowFull: "#0891b2",
  CPAPPressure: "#dc2626",
  PressureMeasured: "#ea580c",
  ObstructLevel: "#f59e0b",
  IPAP: "#059669",
  EPAP: "#7c3aed",
};

const DEFAULT_CHANNELS = ["RespFlow", "Pressure", "LeakFlowBreath"];
const WINDOW_SECONDS = 300; // 5 minutes per view

interface Props {
  nightId: number;
}

export function SignalViewer({ nightId }: Props) {
  const { data: filesData, loading: filesLoading } = useApi<SignalFilesResponse>(
    `/api/signals/night/${nightId}`,
  );

  const [selectedFile, setSelectedFile] = useState<SignalFileInfo | null>(null);
  const [selectedChannels, setSelectedChannels] = useState<string[]>(DEFAULT_CHANNELS);
  const [startTime, setStartTime] = useState(0);
  const [signalData, setSignalData] = useState<SignalDataResponse | null>(null);
  const [loadingData, setLoadingData] = useState(false);

  // Auto-select first file when data loads
  useEffect(() => {
    if (filesData?.signal_files?.length && !selectedFile) {
      setSelectedFile(filesData.signal_files[0]);
    }
  }, [filesData, selectedFile]);

  // Fetch signal data when file, channels, or time range changes
  const fetchData = useCallback(async () => {
    if (!selectedFile) return;
    setLoadingData(true);
    try {
      const params = new URLSearchParams({
        start: startTime.toString(),
        duration: WINDOW_SECONDS.toString(),
        channels: selectedChannels.join(","),
      });
      const res = await fetch(`/api/signals/data/${selectedFile.id}?${params}`);
      if (res.ok) {
        const data: SignalDataResponse = await res.json();
        setSignalData(data);
      }
    } catch {
      // Silently fail
    } finally {
      setLoadingData(false);
    }
  }, [selectedFile, startTime, selectedChannels]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (filesLoading) return <p className="text-gray-500 text-sm">Loading signals...</p>;
  if (!filesData?.signal_files?.length) return null;

  const totalDuration = selectedFile?.duration_seconds ?? 0;
  const maxStart = Math.max(0, totalDuration - WINDOW_SECONDS);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-600">Signal Waveforms</h3>

        {/* Session selector if multiple signal files */}
        {filesData.signal_files.length > 1 && (
          <select
            className="text-xs border border-gray-200 rounded px-2 py-1"
            value={selectedFile?.id ?? ""}
            onChange={(e) => {
              const file = filesData.signal_files.find((f) => f.id === Number(e.target.value));
              if (file) {
                setSelectedFile(file);
                setStartTime(0);
              }
            }}
          >
            {filesData.signal_files.map((f) => (
              <option key={f.id} value={f.id}>
                Session {f.session_index + 1} ({formatDuration(f.duration_seconds)})
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Channel toggles */}
      <div className="flex flex-wrap gap-2">
        {selectedFile?.channels.map((ch) => (
          <button
            type="button"
            key={ch.label}
            onClick={() => {
              setSelectedChannels((prev) =>
                prev.includes(ch.label) ? prev.filter((c) => c !== ch.label) : [...prev, ch.label],
              );
            }}
            className={`text-xs px-2 py-1 rounded border transition-colors ${
              selectedChannels.includes(ch.label)
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-gray-200 text-gray-500 hover:bg-gray-50"
            }`}
          >
            <span
              className="inline-block w-2 h-2 rounded-full mr-1"
              style={{
                backgroundColor: CHANNEL_COLORS[ch.label] || "#6b7280",
              }}
            />
            {ch.label} ({ch.unit})
          </button>
        ))}
      </div>

      {/* Time navigation */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setStartTime(Math.max(0, startTime - WINDOW_SECONDS))}
          disabled={startTime <= 0}
          className="text-xs px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-50"
        >
          &larr; Earlier
        </button>
        <span className="text-xs text-gray-500">
          {formatTime(startTime)} &ndash; {formatTime(startTime + WINDOW_SECONDS)}
          {" / "}
          {formatDuration(totalDuration)}
        </span>
        <button
          type="button"
          onClick={() => setStartTime(Math.min(maxStart, startTime + WINDOW_SECONDS))}
          disabled={startTime >= maxStart}
          className="text-xs px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-50"
        >
          Later &rarr;
        </button>

        {/* Slider for quick navigation */}
        <input
          type="range"
          min={0}
          max={maxStart}
          step={60}
          value={startTime}
          onChange={(e) => setStartTime(Number(e.target.value))}
          className="flex-1 h-1.5 accent-blue-600"
        />
      </div>

      {/* Charts */}
      {loadingData && <p className="text-xs text-gray-400">Loading...</p>}

      {signalData &&
        selectedChannels.map((channelLabel) => {
          const channelInfo = signalData.channels[channelLabel];
          if (!channelInfo || channelInfo.values.length === 0) return null;

          const chartData = channelInfo.values.map((v, i) => ({
            time: startTime + (i / channelInfo.sample_count) * WINDOW_SECONDS,
            value: v,
          }));

          const color = CHANNEL_COLORS[channelLabel] || "#6b7280";
          const unit = selectedFile?.channels.find((c) => c.label === channelLabel)?.unit ?? "";

          return (
            <div key={channelLabel} className="border-t border-gray-100 pt-2">
              <p className="text-xs text-gray-500 mb-1">
                {channelLabel} ({unit})
              </p>
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="time"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v: number) => formatTime(v)}
                    domain={[startTime, startTime + WINDOW_SECONDS]}
                  />
                  <YAxis tick={{ fontSize: 10 }} width={45} domain={["auto", "auto"]} />
                  <Tooltip
                    labelFormatter={(v: number) => formatTime(v)}
                    formatter={(v: number) => [v.toFixed(1), channelLabel]}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={color}
                    strokeWidth={1}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          );
        })}
    </div>
  );
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h${m}m`;
  return `${m}m`;
}
