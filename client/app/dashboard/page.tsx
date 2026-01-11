"use client";

import { useEffect, useState, useRef } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Monitor, Smartphone, Wifi, MousePointer2, Info, CheckCircle2 } from "lucide-react";

type DashboardState = {
  server_running: boolean;
  client_connected: boolean;
  port: number;
  protocol: string;
  session_id: string;
  mouse_x: number;
  mouse_y: number;
  last_click: string;
  local_ip: string;
};

export default function Dashboard() {
  const [state, setState] = useState<DashboardState>({
    server_running: true,
    client_connected: false,
    port: 8000,
    protocol: "WebSocket",
    session_id: "0pixna",
    mouse_x: 0,
    mouse_y: 0,
    last_click: "None",
    local_ip: "127.0.0.1",
  });

  const [connectionUrl, setConnectionUrl] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const host = state.local_ip !== "127.0.0.1" ? state.local_ip : window.location.hostname;
    const port = window.location.port || "8000";
    const protocol = window.location.protocol === "https:" ? "https" : "http";
    const url = `${protocol}://${host}:${port}/?session=${state.session_id}`;
    setConnectionUrl(url);

    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsProtocol}://${window.location.hostname}:${port}/dashboard-ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.t === "dashboard.state") {
          setState(data.state);
        }
      } catch (err) {
        console.error("Failed to parse dashboard state", err);
      }
    };

    return () => {
      ws.close();
    };
  }, [state.session_id, state.local_ip]);

  return (
    <div className="min-h-screen bg-[#0f172a] text-slate-200 p-8 font-sans">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <header className="flex flex-col items-center mb-12">
          <div className="flex items-center gap-3 mb-2">
            <Monitor className="w-8 h-8 text-blue-400" />
            <h1 className="text-3xl font-bold tracking-tight text-white">Air Mouse Server</h1>
          </div>
          <p className="text-slate-400">Control your desktop with your phone</p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column: QR Code */}
          <div className="bg-[#1e293b] rounded-2xl p-8 border border-slate-700/50 shadow-xl">
            <div className="flex items-center gap-2 mb-6">
              <Smartphone className="w-5 h-5 text-blue-400" />
              <h2 className="text-xl font-semibold text-white">Scan to Connect</h2>
            </div>

            <div className="bg-white p-6 rounded-xl inline-block mb-8 mx-auto block w-fit shadow-inner">
              {connectionUrl && (
                <QRCodeSVG value={connectionUrl} size={256} level="H" />
              )}
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1 block">Session ID</label>
                <div className="bg-[#0f172a] p-3 rounded-lg font-mono text-blue-400 border border-slate-700/50">
                  {state.session_id}
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1 block">Connection URL</label>
                <div className="bg-[#0f172a] p-3 rounded-lg font-mono text-xs text-blue-300/70 break-all border border-slate-700/50">
                  {connectionUrl}
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Status & Activity */}
          <div className="space-y-8">
            {/* Server Status */}
            <div className="bg-[#1e293b] rounded-2xl p-8 border border-slate-700/50 shadow-xl">
              <div className="flex items-center gap-2 mb-6">
                <Wifi className="w-5 h-5 text-green-400" />
                <h2 className="text-xl font-semibold text-white">Server Status</h2>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-[#0f172a] rounded-xl border border-slate-700/30">
                  <span className="text-slate-400">Server</span>
                  <div className="flex items-center gap-2 text-green-400 font-medium">
                    <CheckCircle2 className="w-4 h-4" />
                    Running
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 bg-[#0f172a] rounded-xl border border-slate-700/30">
                  <span className="text-slate-400">Client Connection</span>
                  <div className={`flex items-center gap-2 font-medium ${state.client_connected ? 'text-green-400' : 'text-slate-500'}`}>
                    <CheckCircle2 className="w-4 h-4" />
                    {state.client_connected ? 'Connected' : 'Disconnected'}
                  </div>
                </div>
                <div className="flex items-center justify-between px-4">
                  <span className="text-slate-500 text-sm">Port</span>
                  <span className="text-slate-300 font-mono">{state.port}</span>
                </div>
                <div className="flex items-center justify-between px-4">
                  <span className="text-slate-500 text-sm">Protocol</span>
                  <span className="text-slate-300 font-mono">{state.protocol}</span>
                </div>
              </div>
            </div>

            {/* Mouse Activity */}
            <div className="bg-[#1e293b] rounded-2xl p-8 border border-slate-700/50 shadow-xl">
              <div className="flex items-center gap-2 mb-6">
                <MousePointer2 className="w-5 h-5 text-purple-400" />
                <h2 className="text-xl font-semibold text-white">Mouse Activity</h2>
              </div>

              <div className="space-y-4">
                <div className="p-4 bg-[#0f172a] rounded-xl border border-slate-700/30">
                  <label className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 block">Position</label>
                  <div className="text-xl font-mono text-white">
                    X: <span className="text-blue-400">{state.mouse_x.toFixed(0)}</span> | Y: <span className="text-blue-400">{state.mouse_y.toFixed(0)}</span>
                  </div>
                </div>
                <div className="p-4 bg-[#0f172a] rounded-xl border border-slate-700/30">
                  <label className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 block">Last Click</label>
                  <div className="text-slate-300 font-medium">{state.last_click}</div>
                </div>
                <div className="flex items-center gap-2 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-blue-300 text-sm">
                  <CheckCircle2 className="w-4 h-4" />
                  Ready to receive input from your phone
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* How to Connect */}
        <div className="mt-8 bg-[#1e293b] rounded-2xl p-8 border border-slate-700/50 shadow-xl">
          <div className="flex items-center gap-2 mb-6">
            <Info className="w-5 h-5 text-slate-400" />
            <h2 className="text-xl font-semibold text-white">How to Connect</h2>
          </div>
          <ol className="space-y-3 text-slate-400 list-decimal list-inside">
            <li>Open your phone's camera app or QR code scanner</li>
            <li>Scan the QR code displayed above</li>
            <li>Your phone will open the Air Mouse control interface</li>
            <li>Use your phone's touchscreen to control the mouse cursor</li>
            <li>Tap the Left/Right buttons to perform clicks</li>
          </ol>
        </div>
      </div>

      <style jsx global>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body {
          font-family: 'Inter', sans-serif;
        }
      `}</style>
    </div>
  );
}
