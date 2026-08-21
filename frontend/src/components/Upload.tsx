import { useCallback, useState } from "react";
import { useApi } from "../hooks/useApi";

interface ScanResult {
  status: string;
  devices: string[];
  nights_imported: number;
  nights_skipped: number;
  errors: string[];
}

interface ScanStatus {
  mounted: boolean;
  path: string;
}

export function Upload() {
  const { data: status } = useApi<ScanStatus>("/api/scan/status");
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/scan", { method: "POST" });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      const data: ScanResult = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }, []);

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Import CPAP Data</h2>

      {/* Status indicator */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h3 className="text-sm font-medium text-gray-600 mb-2">SD Card Mount</h3>
        {status?.mounted ? (
          <div className="flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500" />
            <span className="text-sm text-gray-700">
              Data detected at <code className="bg-gray-100 px-1 rounded">{status.path}</code>
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-400" />
            <span className="text-sm text-gray-500">
              No data found. Copy your CPAP SD card contents to the{" "}
              <code className="bg-gray-100 px-1 rounded">sdcard/</code> folder.
            </span>
          </div>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
        <p className="font-medium mb-1">How to import:</p>
        <ol className="list-decimal ml-4 space-y-1">
          <li>Insert your Prisma CPAP SD card or connect via USB</li>
          <li>
            Copy the contents to the <code className="bg-blue-100 px-1 rounded">sdcard/</code>{" "}
            folder next to docker-compose.yml
          </li>
          <li>Click "Scan & Import" below</li>
        </ol>
        <p className="mt-2 text-blue-600">
          Already imported nights are skipped automatically — safe to re-scan anytime.
        </p>
      </div>

      {/* Scan button */}
      <button
        type="button"
        onClick={handleScan}
        disabled={scanning || !status?.mounted}
        className={`px-5 py-2.5 rounded font-medium text-white transition-colors ${
          scanning || !status?.mounted
            ? "bg-gray-400 cursor-not-allowed"
            : "bg-blue-600 hover:bg-blue-700"
        }`}
      >
        {scanning ? "Scanning..." : "Scan & Import"}
      </button>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
          <h3 className="text-sm font-medium text-gray-600">Import Results</h3>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <p className="text-gray-500">Devices</p>
              <p className="font-semibold">{result.devices.join(", ") || "–"}</p>
            </div>
            <div>
              <p className="text-gray-500">Nights Imported</p>
              <p className="font-semibold text-green-600">{result.nights_imported}</p>
            </div>
            <div>
              <p className="text-gray-500">Already Existed</p>
              <p className="font-semibold text-gray-500">{result.nights_skipped}</p>
            </div>
            <div>
              <p className="text-gray-500">Errors</p>
              <p
                className={`font-semibold ${result.errors.length > 0 ? "text-red-600" : "text-gray-500"}`}
              >
                {result.errors.length}
              </p>
            </div>
          </div>

          {result.errors.length > 0 && (
            <div className="mt-2 text-xs text-red-600 space-y-1">
              {result.errors.map((err, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: static error list
                <p key={i}>{err}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
