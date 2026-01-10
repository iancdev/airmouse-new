"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Enabled = {
  camera: boolean;
  accel: boolean;
  gyro: boolean;
  orientation: boolean;
};

type ConnState = "disconnected" | "connecting" | "connected" | "error";

function wsUrl(host: string, port: number) {
  const scheme = typeof location !== "undefined" && location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${host}:${port}/ws`;
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

export default function Home() {
  const [host, setHost] = useState("");
  const [port, setPort] = useState(8000);
  const [sensitivity, setSensitivity] = useState(1);
  const [cameraFps, setCameraFps] = useState(15);
  const [enabled, setEnabled] = useState<Enabled>({
    camera: false,
    accel: true,
    gyro: false,
    orientation: false,
  });

  const [connState, setConnState] = useState<ConnState>("disconnected");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [cameraId, setCameraId] = useState<string>("");

  const scrollStartY = useRef<number | null>(null);
  const lastScrollY = useRef<number | null>(null);

  const isConnected = connState === "connected";

  useEffect(() => {
    if (typeof location === "undefined") return;
    setHost(location.hostname || "localhost");
  }, []);

  const canEnumerate = typeof navigator !== "undefined" && !!navigator.mediaDevices?.enumerateDevices;

  async function refreshCameras() {
    if (!canEnumerate) return;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const vids = devices.filter((d) => d.kind === "videoinput");
    setCameras(vids);
    if (!cameraId && vids[0]?.deviceId) setCameraId(vids[0].deviceId);
  }

  useEffect(() => {
    void refreshCameras();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connectDisabled = useMemo(() => {
    if (!host) return true;
    if (port < 1 || port > 65535) return true;
    if (connState === "connecting" || isConnected) return true;
    return false;
  }, [host, port, connState, isConnected]);

  function sendJson(obj: unknown) {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(obj));
  }

  async function connect() {
    setError(null);
    setConnState("connecting");
    const url = wsUrl(host, port);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      sendJson({ t: "hello", clientVersion: "0.1.0", device: navigator.userAgent });
      sendJson({ t: "config", sensitivity, cameraFps, enabled });
      setConnState("connected");
    };

    ws.onclose = () => {
      wsRef.current = null;
      setConnState("disconnected");
    };

    ws.onerror = () => {
      setConnState("error");
      setError("WebSocket error. Check host/port and that the server is reachable.");
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(String(evt.data));
        if (msg?.t === "error" && typeof msg.message === "string") setError(msg.message);
      } catch {
        // ignore
      }
    };
  }

  function disconnect() {
    wsRef.current?.close();
    wsRef.current = null;
    setConnState("disconnected");
  }

  function setEnabledKey(key: keyof Enabled, value: boolean) {
    setEnabled((prev) => ({ ...prev, [key]: value }));
  }

  function click(button: "left" | "right", state: "down" | "up") {
    sendJson({ t: "input.click", button, state });
  }

  function onScrollPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    (e.target as HTMLDivElement).setPointerCapture(e.pointerId);
    scrollStartY.current = e.clientY;
    lastScrollY.current = e.clientY;
  }

  function onScrollPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (lastScrollY.current == null) return;
    const dy = e.clientY - lastScrollY.current;
    lastScrollY.current = e.clientY;
    const delta = clamp(-dy * 2, -120, 120);
    sendJson({ t: "input.scroll", delta });
  }

  function onScrollPointerUp() {
    scrollStartY.current = null;
    lastScrollY.current = null;
  }

  return (
    <main
      style={{
        maxWidth: 820,
        margin: "0 auto",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>AirMouse</div>
          <div style={{ color: "var(--muted)", fontSize: 13 }}>
            {isConnected ? "Connected" : connState === "connecting" ? "Connecting…" : "Not connected"}
          </div>
        </div>
        {isConnected ? (
          <button
            onClick={disconnect}
            style={{
              background: "transparent",
              color: "var(--danger)",
              border: "1px solid var(--border)",
              padding: "10px 12px",
              borderRadius: 12,
            }}
          >
            Disconnect
          </button>
        ) : null}
      </header>

      {error ? (
        <div style={{ border: "1px solid rgba(255,92,124,0.35)", background: "rgba(255,92,124,0.10)", padding: 12, borderRadius: 12 }}>
          {error}
        </div>
      ) : null}

      {!isConnected ? (
        <section style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 16, padding: 16 }}>
          <div style={{ fontWeight: 700, marginBottom: 10 }}>Connect</div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 140px", gap: 12 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>Server IP / Host</span>
              <input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="192.168.1.50"
                style={{
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  color: "var(--text)",
                }}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>Port</span>
              <input
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
                inputMode="numeric"
                type="number"
                min={1}
                max={65535}
                style={{
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  color: "var(--text)",
                }}
              />
            </label>
          </div>

          <div style={{ height: 12 }} />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>Sensitivity</span>
              <input
                value={sensitivity}
                onChange={(e) => setSensitivity(Number(e.target.value))}
                type="range"
                min={0.1}
                max={5}
                step={0.1}
              />
              <span style={{ color: "var(--muted)", fontSize: 12 }}>{sensitivity.toFixed(1)}</span>
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>Camera FPS</span>
              <input
                value={cameraFps}
                onChange={(e) => setCameraFps(Number(e.target.value))}
                type="range"
                min={5}
                max={60}
                step={1}
              />
              <span style={{ color: "var(--muted)", fontSize: 12 }}>{cameraFps} fps</span>
            </label>
          </div>

          <div style={{ height: 12 }} />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <label style={{ display: "flex", gap: 10, alignItems: "center", padding: 12, borderRadius: 12, border: "1px solid var(--border)" }}>
              <input type="checkbox" checked={enabled.camera} onChange={(e) => setEnabledKey("camera", e.target.checked)} />
              <div>
                <div style={{ fontWeight: 600 }}>Camera</div>
                <div style={{ color: "var(--muted)", fontSize: 12 }}>Visual motion (desk texture)</div>
              </div>
            </label>
            <label style={{ display: "flex", gap: 10, alignItems: "center", padding: 12, borderRadius: 12, border: "1px solid var(--border)" }}>
              <input type="checkbox" checked={enabled.accel} onChange={(e) => setEnabledKey("accel", e.target.checked)} />
              <div>
                <div style={{ fontWeight: 600 }}>Accelerometer</div>
                <div style={{ color: "var(--muted)", fontSize: 12 }}>Motion acceleration samples</div>
              </div>
            </label>
            <label style={{ display: "flex", gap: 10, alignItems: "center", padding: 12, borderRadius: 12, border: "1px solid var(--border)" }}>
              <input type="checkbox" checked={enabled.gyro} onChange={(e) => setEnabledKey("gyro", e.target.checked)} />
              <div>
                <div style={{ fontWeight: 600 }}>Gyroscope</div>
                <div style={{ color: "var(--muted)", fontSize: 12 }}>Rotation rate samples</div>
              </div>
            </label>
            <label style={{ display: "flex", gap: 10, alignItems: "center", padding: 12, borderRadius: 12, border: "1px solid var(--border)" }}>
              <input type="checkbox" checked={enabled.orientation} onChange={(e) => setEnabledKey("orientation", e.target.checked)} />
              <div>
                <div style={{ fontWeight: 600 }}>Orientation</div>
                <div style={{ color: "var(--muted)", fontSize: 12 }}>Alpha/Beta/Gamma</div>
              </div>
            </label>
          </div>

          <div style={{ height: 12 }} />

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
              <div style={{ fontWeight: 700 }}>Camera Selection</div>
              <button
                onClick={() => void refreshCameras()}
                disabled={!canEnumerate}
                style={{
                  background: "transparent",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  padding: "8px 10px",
                  color: "var(--text)",
                }}
              >
                Refresh
              </button>
            </div>
            <select
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value)}
              disabled={!enabled.camera || cameras.length === 0}
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border)",
                borderRadius: 12,
                padding: "10px 12px",
                color: "var(--text)",
              }}
            >
              {cameras.length === 0 ? <option value="">No cameras detected</option> : null}
              {cameras.map((cam, idx) => (
                <option key={cam.deviceId} value={cam.deviceId}>
                  {cam.label || `Camera ${idx + 1}`}
                </option>
              ))}
            </select>
          </div>

          <div style={{ height: 16 }} />

          <button
            onClick={() => void connect()}
            disabled={connectDisabled}
            style={{
              width: "100%",
              background: connectDisabled ? "rgba(255,255,255,0.06)" : "var(--accent)",
              border: "1px solid var(--border)",
              borderRadius: 14,
              padding: "12px 14px",
              color: "var(--text)",
              fontWeight: 700,
            }}
          >
            Connect
          </button>

          <div style={{ marginTop: 12, color: "var(--muted)", fontSize: 12 }}>
            Tip: run the server on your computer, then connect your phone on the same Wi‑Fi.
          </div>
        </section>
      ) : (
        <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <button
            onPointerDown={() => click("left", "down")}
            onPointerUp={() => click("left", "up")}
            onPointerCancel={() => click("left", "up")}
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid var(--border)",
              borderRadius: 18,
              padding: "18px 14px",
              color: "var(--text)",
              fontWeight: 800,
              minHeight: 90,
            }}
          >
            Left Click
          </button>
          <button
            onPointerDown={() => click("right", "down")}
            onPointerUp={() => click("right", "up")}
            onPointerCancel={() => click("right", "up")}
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid var(--border)",
              borderRadius: 18,
              padding: "18px 14px",
              color: "var(--text)",
              fontWeight: 800,
              minHeight: 90,
            }}
          >
            Right Click
          </button>

          <div
            onPointerDown={onScrollPointerDown}
            onPointerMove={onScrollPointerMove}
            onPointerUp={onScrollPointerUp}
            onPointerCancel={onScrollPointerUp}
            style={{
              gridColumn: "1 / -1",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid var(--border)",
              borderRadius: 18,
              padding: 16,
              minHeight: 180,
              touchAction: "none",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "center",
              gap: 8,
            }}
          >
            <div style={{ fontWeight: 800 }}>Scroll</div>
            <div style={{ color: "var(--muted)", fontSize: 12, textAlign: "center" }}>
              Drag up/down here to scroll on the computer.
            </div>
          </div>
        </section>
      )}
    </main>
  );
}

