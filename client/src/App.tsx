import { useState, useEffect, useCallback } from 'react';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import {
  Radio,
  Sliders,
  Wifi,
  WifiOff,
  Settings,
  Headphones,
  Check,
  X,
} from 'lucide-react';

import { RadioPanel } from './components/RadioPanel';
import { VuMeter } from './components/VuMeter';
import { PttConfig } from './components/PttConfig';
import { TranscriptLog } from './components/TranscriptLog';
import {
  AircraftSnapshot,
  AudioLevelPayload,
  DspSettings,
  GatewayInfo,
  PttBinding,
  PttConfig as PttConfigType,
  RadioType,
  SessionInfo,
  TranscriptEntry,
} from './types';

// Default initial telemetry snapshot (WAHI Yogyakarta International)
const DEFAULT_SNAPSHOT: AircraftSnapshot = {
  com1_hz: 118_200_000,
  com2_hz: 121_650_000,
  active_radio: 1,
  lat: -7.9042,
  lon: 110.0528,
  elevation_m: 7.3,
  agl_m: 0.0,
  on_ground: true,
  squawk: 5201,
  qnh_inhg: 29.85,
  groundspeed_ms: 0.0,
  wind_speed: 7.0,
  wind_dir: 100.0,
};

const DEFAULT_PTT_CONFIG: PttConfigType = {
  com1: {
    joystick_button: 0,
    keyboard_key: 'Space',
    mouse_button: null,
  },
  com2: {
    joystick_button: 1,
    keyboard_key: 'KeyT',
    mouse_button: null,
  },
};

const DEFAULT_DSP_SETTINGS: DspSettings = {
  noise_level: 0.03,
  squelch_volume: 0.8,
  bandpass_enabled: true,
};

const INITIAL_TRANSCRIPT: TranscriptEntry[] = [
  {
    id: 'tx-1',
    timestamp: '07:00:00',
    speaker: 'ATIS',
    radio: 'COM1',
    text: 'Yogyakarta International Information Alpha. 0700Z. Wind 100 at 07 knots. Visibility 10 kilometers. Few clouds at 2000 feet. Temperature 29, dewpoint 24. QNH 1011 hectopascals. Departing runway 11.',
    clearanceType: 'WEATHER',
  },
  {
    id: 'tx-2',
    timestamp: '07:02:15',
    speaker: 'Pilot',
    radio: 'COM1',
    text: 'Yogyakarta Ground, Indonesia 123, stand 4, request IFR clearance to Jakarta Halim.',
  },
  {
    id: 'tx-3',
    timestamp: '07:02:28',
    speaker: 'ATC',
    radio: 'COM1',
    text: 'Indonesia 123, Yogyakarta Ground, cleared to Halim via SOVI1A departure, runway 11, climb to flight level 100, squawk 5201.',
    clearanceType: 'CLEARANCE',
  },
];

export default function App() {
  const [snapshot, setSnapshot] = useState<AircraftSnapshot>(DEFAULT_SNAPSHOT);
  const [session, setSession] = useState<SessionInfo>({
    callsign: 'GIA123',
    aircraft_type: 'B738',
  });
  const [pttConfig, setPttConfig] = useState<PttConfigType>(DEFAULT_PTT_CONFIG);
  const [dspSettings, setDspSettings] = useState<DspSettings>(DEFAULT_DSP_SETTINGS);
  const [gatewayInfo, setGatewayInfo] = useState<GatewayInfo>({
    url: 'ws://127.0.0.1:8000/ws/audio',
    connected: true,
  });
  const [audioLevels, setAudioLevels] = useState<AudioLevelPayload>({
    mic_level: 0.0,
    atc_level: 0.0,
    is_transmitting: false,
  });
  const [transcript, setTranscript] = useState<TranscriptEntry[]>(INITIAL_TRANSCRIPT);
  const [isSimConnected, setIsSimConnected] = useState<boolean>(false);
  const [isPttModalOpen, setIsPttModalOpen] = useState<boolean>(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState<boolean>(false);

  // Settings form states
  const [formCallsign, setFormCallsign] = useState(session.callsign);
  const [formAircraftType, setFormAircraftType] = useState(session.aircraft_type);
  const [formGatewayUrl, setFormGatewayUrl] = useState(gatewayInfo.url);
  const [formNoiseLevel, setFormNoiseLevel] = useState(dspSettings.noise_level);
  const [formSquelchVolume, setFormSquelchVolume] = useState(dspSettings.squelch_volume);
  const [formBandpass, setFormBandpass] = useState(dspSettings.bandpass_enabled);

  const tauriActive = isTauri();

  // Load initial backend state and wire event listeners
  useEffect(() => {
    let unlistenTelemetry: UnlistenFn | undefined;
    let unlistenSimConnected: UnlistenFn | undefined;
    let unlistenAudio: UnlistenFn | undefined;
    let unlistenPtt: UnlistenFn | undefined;
    let unlistenTranscript: UnlistenFn | undefined;
    let unlistenPttConfig: UnlistenFn | undefined;

    async function initTauri() {
      if (!tauriActive) {
        setIsSimConnected(true);
        return;
      }

      try {
        const snap = await invoke<AircraftSnapshot>('get_aircraft_state');
        setSnapshot(snap);
      } catch (err) {
        console.warn('Initial aircraft state error:', err);
      }

      try {
        const isConnected = await invoke<boolean>('is_sim_connected');
        setIsSimConnected(isConnected);
      } catch (err) {
        console.warn('Initial sim connection error:', err);
      }

      try {
        const sess = await invoke<SessionInfo>('get_session_info');
        setSession(sess);
        setFormCallsign(sess.callsign);
        setFormAircraftType(sess.aircraft_type);
      } catch (err) {
        console.warn('Initial session info error:', err);
      }

      try {
        const ptt = await invoke<PttConfigType>('get_ptt_config');
        setPttConfig(ptt);
      } catch (err) {
        console.warn('Initial PTT config error:', err);
      }

      try {
        const dsp = await invoke<DspSettings>('get_dsp_settings');
        setDspSettings(dsp);
        setFormNoiseLevel(dsp.noise_level);
        setFormSquelchVolume(dsp.squelch_volume);
        setFormBandpass(dsp.bandpass_enabled);
      } catch (err) {
        console.warn('Initial DSP settings error:', err);
      }

      // 1. Telemetry event listener
      unlistenTelemetry = await listen<AircraftSnapshot>('telemetry_update', (event) => {
        setSnapshot(event.payload);
      });

      // Simulator connection status event listener
      unlistenSimConnected = await listen<boolean>('sim_connected_update', (event) => {
        setIsSimConnected(event.payload);
      });

      // 2. Audio level event listener
      unlistenAudio = await listen<AudioLevelPayload>('audio_level_update', (event) => {
        setAudioLevels(event.payload);
      });

      // 3. Ptt state transition event listener
      unlistenPtt = await listen<{ radio?: RadioType; Pressed?: { radio: RadioType }; Released?: { radio: RadioType } }>(
        'ptt_state_change',
        (event) => {
          const isPressed = !!event.payload.Pressed;
          setAudioLevels((prev) => ({
            ...prev,
            is_transmitting: isPressed,
          }));
        }
      );

      // 4. ATC transcript update event listener
      unlistenTranscript = await listen<TranscriptEntry>('atc_transcript_update', (event) => {
        setTranscript((prev) => [...prev, event.payload]);
      });

      // 5. PTT config update event listener (learning mode capture or background sync)
      unlistenPttConfig = await listen<PttConfigType>('ptt_config_updated', (event) => {
        setPttConfig(event.payload);
      });
    }

    initTauri();

    return () => {
      unlistenTelemetry?.();
      unlistenSimConnected?.();
      unlistenAudio?.();
      unlistenPtt?.();
      unlistenTranscript?.();
      unlistenPttConfig?.();
    };
  }, [tauriActive]);

  // Push-To-Talk manual mouse trigger handlers
  const handlePttMouseDown = useCallback(async () => {
    setAudioLevels((prev) => ({ ...prev, is_transmitting: true, mic_level: 0.65 }));
    if (tauriActive) {
      const radioType: RadioType = snapshot.active_radio === 2 ? 'Com2' : 'Com1';
      try {
        await invoke('trigger_ptt_press', { radio: radioType });
      } catch (err) {
        console.error('trigger_ptt_press error:', err);
      }
    }
  }, [tauriActive, snapshot.active_radio]);

  const handlePttMouseUp = useCallback(async () => {
    setAudioLevels((prev) => ({ ...prev, is_transmitting: false, mic_level: 0.0 }));
    if (tauriActive) {
      const radioType: RadioType = snapshot.active_radio === 2 ? 'Com2' : 'Com1';
      try {
        await invoke('trigger_ptt_release', { radio: radioType });
      } catch (err) {
        console.error('trigger_ptt_release error:', err);
      }
    }
  }, [tauriActive, snapshot.active_radio]);

  // Radio selection toggle
  const handleSelectRadio = useCallback(
    (radio: 1 | 2) => {
      setSnapshot((prev) => ({ ...prev, active_radio: radio }));
    },
    []
  );

  // Save PTT Binding
  const handleSavePttBinding = useCallback(
    async (radio: RadioType, binding: PttBinding) => {
      if (tauriActive) {
        try {
          const updated = await invoke<PttConfigType>('set_ptt_binding', { radio, binding });
          setPttConfig(updated);
        } catch (err) {
          console.error('set_ptt_binding error:', err);
        }
      } else {
        setPttConfig((prev) => ({
          ...prev,
          [radio === 'Com1' ? 'com1' : 'com2']: binding,
        }));
      }
    },
    [tauriActive]
  );

  // PTT Learning
  const handleStartPttLearning = useCallback(
    async (radio: RadioType) => {
      if (tauriActive) {
        try {
          await invoke('start_ptt_learning', { radio });
        } catch (err) {
          console.error('start_ptt_learning error:', err);
        }
      }
    },
    [tauriActive]
  );

  const handleStopPttLearning = useCallback(async () => {
    if (tauriActive) {
      try {
        await invoke('stop_ptt_learning');
      } catch (err) {
        console.error('stop_ptt_learning error:', err);
      }
    }
  }, [tauriActive]);

  // Save Settings Modal
  const handleSaveSettings = async () => {
    if (tauriActive) {
      try {
        const updatedSess = await invoke<SessionInfo>('set_callsign', {
          callsign: formCallsign,
          aircraftType: formAircraftType,
        });
        setSession(updatedSess);

        const updatedDsp = await invoke<DspSettings>('set_dsp_settings', {
          noiseLevel: formNoiseLevel,
          squelchVolume: formSquelchVolume,
          bandpassEnabled: formBandpass,
        });
        setDspSettings(updatedDsp);

        const updatedGw = await invoke<GatewayInfo>('connect_gateway', {
          url: formGatewayUrl,
        });
        setGatewayInfo(updatedGw);
      } catch (err) {
        console.error('Error saving settings:', err);
      }
    } else {
      setSession({
        callsign: formCallsign.toUpperCase(),
        aircraft_type: formAircraftType.toUpperCase(),
      });
      setDspSettings({
        noise_level: formNoiseLevel,
        squelch_volume: formSquelchVolume,
        bandpass_enabled: formBandpass,
      });
      setGatewayInfo({
        url: formGatewayUrl,
        connected: formGatewayUrl.startsWith('ws://') || formGatewayUrl.startsWith('wss://'),
      });
    }
    setIsSettingsModalOpen(false);
  };

  const activeRadioName = snapshot.active_radio === 2 ? 'COM2' : 'COM1';

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-emerald-500 selection:text-black">
      {/* Top Cockpit Navigation Bar */}
      <header className="flex flex-wrap items-center justify-between border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 py-3.5 gap-4 sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
            <Radio className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-extrabold tracking-tight text-slate-100 uppercase">
                Wilco AI
              </h1>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-semibold">
                ATC Companion
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
              <span className="text-emerald-400 font-bold">{session.callsign}</span>
              <span>•</span>
              <span>{session.aircraft_type}</span>
            </div>
          </div>
        </div>

        {/* Global Status Badges & Quick Action Controls */}
        <div className="flex items-center gap-3">
          {/* Simulator Status */}
          <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-950 border border-slate-800 text-xs font-mono">
            {isSimConnected ? (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span className="text-slate-300">X-Plane 12</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
                <span className="text-slate-400">Sim Standby</span>
              </>
            )}
          </div>

          {/* AI Gateway Status */}
          <div className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-950 border border-slate-800 text-xs font-mono">
            {gatewayInfo.connected ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-slate-300">Gateway OK</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-rose-400" />
                <span className="text-rose-400">Gateway Off</span>
              </>
            )}
          </div>

          {/* PTT Configuration Modal Button */}
          <button
            onClick={() => setIsPttModalOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-750 text-slate-200 border border-slate-700 text-xs font-semibold tracking-wider transition-colors"
          >
            <Sliders className="w-4 h-4 text-emerald-400" />
            <span>PTT SETUP</span>
          </button>

          {/* Settings Modal Button */}
          <button
            onClick={() => setIsSettingsModalOpen(true)}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-750 text-slate-300 border border-slate-700 transition-colors"
            title="Session & DSP Settings"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main Glass Cockpit Grid */}
      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-[1600px] w-full mx-auto">
        {/* Left Column: Radio Panel & Audio VU Meters */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <RadioPanel
            snapshot={snapshot}
            isSimConnected={isSimConnected}
            onSelectRadio={handleSelectRadio}
          />

          <VuMeter
            levels={audioLevels}
            activeRadioName={activeRadioName}
            onPttMouseDown={handlePttMouseDown}
            onPttMouseUp={handlePttMouseUp}
          />
        </div>

        {/* Right Column: Live Communications Transcript Feed */}
        <div className="lg:col-span-7 flex flex-col">
          <TranscriptLog
            entries={transcript}
            onClear={() => setTranscript([])}
          />
        </div>
      </main>

      {/* PTT Hardware Setup Modal */}
      <PttConfig
        config={pttConfig}
        isOpen={isPttModalOpen}
        onClose={() => setIsPttModalOpen(false)}
        onSaveBinding={handleSavePttBinding}
        onStartLearning={handleStartPttLearning}
        onStopLearning={handleStopPttLearning}
      />

      {/* Session & DSP Settings Modal */}
      {isSettingsModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between p-5 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-400">
                  <Settings className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100">
                    Flight Session & VHF Audio Settings
                  </h3>
                  <p className="text-xs text-slate-400">
                    Configure callsign, gateway endpoint, and VHF transceiver DSP
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsSettingsModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {/* Callsign & Aircraft Type */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300">Callsign</label>
                  <input
                    type="text"
                    value={formCallsign}
                    onChange={(e) => setFormCallsign(e.target.value.toUpperCase())}
                    placeholder="e.g. N172SP / DAL452"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono text-emerald-400 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300">Aircraft Type</label>
                  <input
                    type="text"
                    value={formAircraftType}
                    onChange={(e) => setFormAircraftType(e.target.value.toUpperCase())}
                    placeholder="e.g. C172 / B738"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono text-cyan-400 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Gateway WebSocket URL */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300">
                  Python AI Gateway WebSocket URL
                </label>
                <input
                  type="text"
                  value={formGatewayUrl}
                  onChange={(e) => setFormGatewayUrl(e.target.value)}
                  placeholder="ws://127.0.0.1:8000/ws/audio"
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500"
                />
              </div>

              {/* DSP Audio Settings */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-4">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
                  <Headphones className="w-4 h-4 text-emerald-400" />
                  <span>VHF Radio DSP Audio Pipeline</span>
                </div>

                {/* Noise Gain Slider */}
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>VHF Carrier White Noise Level</span>
                    <span className="font-mono text-emerald-400">
                      {(formNoiseLevel * 100).toFixed(0)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="0.2"
                    step="0.01"
                    value={formNoiseLevel}
                    onChange={(e) => setFormNoiseLevel(parseFloat(e.target.value))}
                    className="w-full accent-emerald-500 cursor-pointer"
                  />
                </div>

                {/* Squelch Volume Slider */}
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Squelch Click Transient Volume</span>
                    <span className="font-mono text-emerald-400">
                      {(formSquelchVolume * 100).toFixed(0)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={formSquelchVolume}
                    onChange={(e) => setFormSquelchVolume(parseFloat(e.target.value))}
                    className="w-full accent-emerald-500 cursor-pointer"
                  />
                </div>

                {/* Bandpass Filter Toggle */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-850">
                  <div className="text-xs">
                    <div className="font-medium text-slate-300">
                      VHF Aviation Bandpass (300 Hz - 3200 Hz)
                    </div>
                    <div className="text-[11px] text-slate-500">
                      4th-order cascaded biquad radio coloration
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={formBandpass}
                    onChange={(e) => setFormBandpass(e.target.checked)}
                    className="w-4 h-4 accent-emerald-500 rounded cursor-pointer"
                  />
                </div>
              </div>
            </div>

            <div className="p-4 bg-slate-950/80 border-t border-slate-800 flex justify-end gap-3">
              <button
                onClick={() => setIsSettingsModalOpen(false)}
                className="py-2 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveSettings}
                className="py-2 px-5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold tracking-wider flex items-center gap-1.5 shadow-md shadow-emerald-950"
              >
                <Check className="w-4 h-4" />
                <span>SAVE CHANGES</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
