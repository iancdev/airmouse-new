"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Enabled = {
  camera: boolean;
  accel: boolean;
  gyro: boolean;
  orientation: boolean;
};

type ConnState = "disconnected" | "connecting" | "connected" | "error";

type PreparedCamera = {
  stream: MediaStream;
  video: HTMLVideoElement;
};

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
  const [smoothingHalfLifeMs, setSmoothingHalfLifeMs] = useState(80);
  const [deadzonePx, setDeadzonePx] = useState(0.25);
  const [enabled, setEnabled] = useState<Enabled>({
    camera: false,
    accel: true,
    gyro: false,
    orientation: false,
  });

  const [connState, setConnState] = useState<ConnState>("disconnected");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const ioStopRef = useRef<(() => void) | null>(null);

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

  async function requestMotionPermissions() {
    const anyWindow = window as any;
    if (enabled.accel || enabled.gyro) {
      const DME = anyWindow.DeviceMotionEvent;
      if (DME && typeof DME.requestPermission === "function") {
        const res = await DME.requestPermission();
        if (res !== "granted") throw new Error("Motion permission was not granted");
      }
    }
    if (enabled.orientation) {
      const DOE = anyWindow.DeviceOrientationEvent;
      if (DOE && typeof DOE.requestPermission === "function") {
        const res = await DOE.requestPermission();
        if (res !== "granted") throw new Error("Orientation permission was not granted");
      }
    }
  }

  function startImuStreaming(ws: WebSocket) {
    if (!enabled.accel && !enabled.gyro && !enabled.orientation) return () => {};
    const latest: Record<string, number> = {};

    const onMotion = (e: DeviceMotionEvent) => {
      latest.ts = Date.now();
      if (enabled.accel) {
        const a = e.acceleration ?? e.accelerationIncludingGravity;
        if (a) {
          if (typeof a.x === "number") latest.ax = a.x;
          if (typeof a.y === "number") latest.ay = a.y;
          if (typeof a.z === "number") latest.az = a.z;
        }
      }
      if (enabled.gyro) {
        const r = e.rotationRate;
        if (r) {
          if (typeof r.alpha === "number") latest.gx = r.alpha;
          if (typeof r.beta === "number") latest.gy = r.beta;
          if (typeof r.gamma === "number") latest.gz = r.gamma;
        }
      }
    };

    const onOrientation = (e: DeviceOrientationEvent) => {
      if (!enabled.orientation) return;
      latest.ts = Date.now();
      if (typeof e.alpha === "number") latest.alpha = e.alpha;
      if (typeof e.beta === "number") latest.beta = e.beta;
      if (typeof e.gamma === "number") latest.gamma = e.gamma;
    };

    window.addEventListener("devicemotion", onMotion);
    window.addEventListener("deviceorientation", onOrientation);

    const intervalId = window.setInterval(() => {
      if (ws.readyState !== WebSocket.OPEN) return;
      if (typeof latest.ts !== "number") return;
      sendJson({ t: "imu.sample", ...latest });
    }, 33);

    return () => {
      window.removeEventListener("devicemotion", onMotion);
      window.removeEventListener("deviceorientation", onOrientation);
      window.clearInterval(intervalId);
    };
  }

  function startCameraStreaming(ws: WebSocket, preparedCamera: PreparedCamera | null) {
    if (!enabled.camera || !preparedCamera) return () => {};
    const { stream, video } = preparedCamera;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas is not available");

    let seq = 0;
    let inFlight = false;
    const intervalMs = Math.max(4, 1000 / cameraFps);

    const intervalId = window.setInterval(() => {
      if (inFlight) return;
      if (ws.readyState !== WebSocket.OPEN) return;
      const vw = video.videoWidth;
      const vh = video.videoHeight;
      if (!vw || !vh) return;

      const targetW = 320;
      const targetH = Math.max(1, Math.round((vh / vw) * targetW));
      canvas.width = targetW;
      canvas.height = targetH;
      ctx.drawImage(video, 0, 0, targetW, targetH);

      inFlight = true;
      canvas.toBlob(
        async (blob) => {
          try {
            if (!blob) return;
            const buf = await blob.arrayBuffer();
            ws.send(
              JSON.stringify({
                t: "cam.frame",
                seq,
                ts: Date.now(),
                width: targetW,
                height: targetH,
                mime: blob.type || "image/jpeg",
              })
            );
            ws.send(buf);
            seq += 1;
          } finally {
            inFlight = false;
          }
        },
        "image/jpeg",
        0.6
      );
    }, intervalMs);

    return () => {
      window.clearInterval(intervalId);
      stream.getTracks().forEach((t) => t.stop());
      video.srcObject = null;
    };
  }

  function startIo(ws: WebSocket, preparedCamera: PreparedCamera | null) {
    const stops: Array<() => void> = [];
    stops.push(startImuStreaming(ws));
    stops.push(startCameraStreaming(ws, preparedCamera));
    return () => {
      for (const stop of stops) stop();
    };
  }

  async function connect() {
    setError(null);
    setConnState("connecting");

    ioStopRef.current?.();
    ioStopRef.current = null;

    let preparedCamera: PreparedCamera | null = null;
    try {
      await requestMotionPermissions();
      if (enabled.camera) {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera API not available in this browser");
        const constraints: MediaStreamConstraints = {
          audio: false,
          video: {
            deviceId: cameraId ? { exact: cameraId } : undefined,
            facingMode: "environment",
            width: { ideal: 640 },
            height: { ideal: 480 },
            frameRate: { ideal: cameraFps },
          },
        };
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        const video = document.createElement("video");
        video.playsInline = true;
        video.muted = true;
        video.srcObject = stream;
        await video.play();
        preparedCamera = { stream, video };
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to get permissions";
      setError(msg);
      setConnState("error");
      preparedCamera?.stream.getTracks().forEach((t) => t.stop());
      return;
    }

    const url = wsUrl(host, port);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      try {
        sendJson({ t: "hello", clientVersion: "0.1.0", device: navigator.userAgent });
        sendJson({
          t: "config",
          sensitivity,
          cameraFps,
          enabled,
          screenAngle: window.screen?.orientation?.angle ?? 0,
          smoothingHalfLifeMs,
          deadzonePx,
        });

        ioStopRef.current = startIo(ws, preparedCamera);
        setConnState("connected");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to start sensors/camera";
        setError(msg);
        setConnState("error");
        ws.close();
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      ioStopRef.current?.();
      ioStopRef.current = null;
      preparedCamera?.stream.getTracks().forEach((t) => t.stop());
      setConnState("disconnected");
    };

    ws.onerror = () => {
      setConnState("error");
      setError("WebSocket error. Check host/port and that the server is reachable.");
      preparedCamera?.stream.getTracks().forEach((t) => t.stop());
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
    ioStopRef.current?.();
    ioStopRef.current = null;
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
                max={240}
                step={1}
              />
              <span style={{ color: "var(--muted)", fontSize: 12 }}>{cameraFps} fps</span>
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>Smoothing</span>
              <input
                value={smoothingHalfLifeMs}
                onChange={(e) => setSmoothingHalfLifeMs(Number(e.target.value))}
                type="range"
                min={0}
                max={250}
                step={5}
              />
              <span style={{ color: "var(--muted)", fontSize: 12 }}>{smoothingHalfLifeMs} ms</span>
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>Deadzone</span>
              <input
                value={deadzonePx}
                onChange={(e) => setDeadzonePx(Number(e.target.value))}
                type="range"
                min={0}
                max={3}
                step={0.05}
              />
              <span style={{ color: "var(--muted)", fontSize: 12 }}>{deadzonePx.toFixed(2)} px</span>
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
