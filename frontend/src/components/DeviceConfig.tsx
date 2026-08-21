import { useApi } from "../hooks/useApi";

interface ConfigParam {
  section: string;
  param_id: number;
  name: string;
  raw_value: string;
  display_value: string;
}

interface DeviceData {
  serial_number: string;
  device_type: string;
  firmware_version: string;
  config: ConfigParam[];
}

export function DeviceConfig() {
  const { data, loading, error } = useApi<DeviceData>("/api/device");

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) {
    return <p className="text-gray-500">No device data available. Upload a .pcfg file first.</p>;
  }
  if (!data) return null;

  const oblParams = data.config.filter((c) => c.section === "OBL");
  const optParams = data.config.filter((c) => c.section === "OPT");

  return (
    <div className="space-y-6">
      {/* Device info */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-sm font-medium text-gray-600 mb-3">Device</h2>
        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <dt className="text-gray-500">Serial Number</dt>
            <dd className="font-mono font-medium">{data.serial_number}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Device Type</dt>
            <dd className="font-medium">{data.device_type || "–"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Firmware</dt>
            <dd className="font-medium">{data.firmware_version || "–"}</dd>
          </div>
        </dl>
      </div>

      {/* Prescribed settings (OBL) */}
      <ConfigTable title="Prescribed Settings (OBL)" params={oblParams} />

      {/* User settings (OPT) */}
      <ConfigTable title="User Settings (OPT)" params={optParams} />
    </div>
  );
}

function ConfigTable({
  title,
  params,
}: {
  title: string;
  params: ConfigParam[];
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200">
      <div className="px-4 py-3 border-b border-gray-100">
        <h2 className="text-sm font-medium text-gray-600">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-4 py-2 text-left">ID</th>
              <th className="px-4 py-2 text-left">Parameter</th>
              <th className="px-4 py-2 text-left">Value</th>
              <th className="px-4 py-2 text-left text-gray-400">Raw</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {params.map((p) => (
              <tr key={p.param_id} className="hover:bg-gray-50">
                <td className="px-4 py-1.5 font-mono text-gray-400">{p.param_id}</td>
                <td className="px-4 py-1.5">{p.name}</td>
                <td className="px-4 py-1.5 font-medium">{p.display_value}</td>
                <td className="px-4 py-1.5 text-gray-400 font-mono">{p.raw_value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
