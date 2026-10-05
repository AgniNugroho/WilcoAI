import React from 'react';
import { Mic, Volume2, Radio, Activity } from 'lucide-react';
import { AudioLevelPayload } from '../types';

interface VuMeterProps {
  levels: AudioLevelPayload;
  activeRadioName: string;
  onPttMouseDown?: () => void;
  onPttMouseUp?: () => void;
}

// Convert normalized RMS (0.0 .. 1.0) to approximate dB representation (-40 dB .. 0 dB)
function rmsToDb(rms: number): number {
  if (rms <= 0.001) return -40;
  const db = 20 * Math.log10(rms);
  return Math.max(-40, Math.min(0, db));
}

// Render segmented LED-style VU bar
const SegmentedMeter: React.FC<{
  level: number;
  totalSegments?: number;
  peakColor?: string;
}> = ({ level, totalSegments = 24 }) => {
  const activeSegments = Math.round(level * totalSegments);

  return (
    <div className="flex items-center gap-1 w-full bg-slate-950/80 p-1.5 rounded-md border border-slate-800/80">
      {Array.from({ length: totalSegments }).map((_, idx) => {
        const isActive = idx < activeSegments;
        const ratio = idx / totalSegments;

        // Color coding: Green (< 65%), Amber (65% - 85%), Red (> 85%)
        let segmentColor = 'bg-slate-800';
        if (isActive) {
          if (ratio > 0.85) {
            segmentColor = 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.7)]';
          } else if (ratio > 0.65) {
            segmentColor = 'bg-amber-400 shadow-[0_0_5px_rgba(251,191,36,0.6)]';
          } else {
            segmentColor = 'bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.5)]';
          }
        }

        return (
          <div
            key={idx}
            className={`h-3.5 flex-1 rounded-sm transition-all duration-75 ${segmentColor}`}
          />
        );
      })}
    </div>
  );
};

export const VuMeter: React.FC<VuMeterProps> = ({
  levels,
  activeRadioName,
  onPttMouseDown,
  onPttMouseUp,
}) => {
  const micDb = rmsToDb(levels.mic_level);
  const atcDb = rmsToDb(levels.atc_level);
  const isAtcActive = levels.atc_level > 0.05;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col gap-4">
      {/* Header and TX / RX Transmit Badge */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <Activity className="w-5 h-5 text-emerald-400" />
          <span className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Audio Levels & Transmit State
          </span>
        </div>

        {/* Dynamic TX/RX Glowing Badge */}
        <div className="flex items-center gap-2">
          {levels.is_transmitting ? (
            <div className="flex items-center gap-2 bg-rose-950/80 border border-rose-500/80 px-3 py-1 rounded-full text-xs font-mono font-bold text-rose-300 animate-pulse shadow-[0_0_15px_rgba(244,63,94,0.4)]">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e]"></span>
              <span>TX ON AIR ({activeRadioName})</span>
            </div>
          ) : isAtcActive ? (
            <div className="flex items-center gap-2 bg-sky-950/80 border border-sky-500/80 px-3 py-1 rounded-full text-xs font-mono font-bold text-sky-300 shadow-[0_0_15px_rgba(14,165,233,0.3)]">
              <span className="w-2.5 h-2.5 rounded-full bg-sky-400 animate-ping"></span>
              <span>RX ATC RECV</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 bg-slate-800/60 border border-slate-700/60 px-3 py-1 rounded-full text-xs font-mono text-slate-400">
              <span className="w-2 h-2 rounded-full bg-slate-500"></span>
              <span>STANDBY</span>
            </div>
          )}
        </div>
      </div>

      {/* Real-time VU Meters */}
      <div className="space-y-4">
        {/* Microphone In Meter */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-slate-300 font-medium">
              <Mic
                className={`w-4 h-4 ${
                  levels.is_transmitting ? 'text-rose-400 animate-pulse' : 'text-slate-400'
                }`}
              />
              <span>Pilot Microphone Input (Mono 24 kHz)</span>
            </div>
            <div className="font-mono text-[11px] text-slate-400">
              {levels.is_transmitting ? (
                <span className="text-emerald-400 font-semibold">{micDb.toFixed(1)} dB</span>
              ) : (
                <span className="text-slate-500">MUTED (IDLE)</span>
              )}
            </div>
          </div>
          <SegmentedMeter level={levels.mic_level} />
          <div className="flex justify-between text-[10px] text-slate-400 font-mono px-1">
            <span>-40 dB</span>
            <span>-24 dB</span>
            <span>-12 dB</span>
            <span>-6 dB</span>
            <span>0 dB</span>
          </div>
        </div>

        {/* ATC Audio Output Meter */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-slate-300 font-medium">
              <Volume2
                className={`w-4 h-4 ${
                  isAtcActive ? 'text-sky-400 animate-bounce' : 'text-slate-400'
                }`}
              />
              <span>ATC Controller Audio Output (VHF DSP Filtered)</span>
            </div>
            <div className="font-mono text-[11px] text-slate-400">
              {isAtcActive ? (
                <span className="text-sky-400 font-semibold">{atcDb.toFixed(1)} dB</span>
              ) : (
                <span className="text-slate-500">SQUELCH CLOSED</span>
              )}
            </div>
          </div>
          <SegmentedMeter level={levels.atc_level} />
          <div className="flex justify-between text-[10px] text-slate-400 font-mono px-1">
            <span>-40 dB</span>
            <span>-24 dB</span>
            <span>-12 dB</span>
            <span>-6 dB</span>
            <span>0 dB</span>
          </div>
        </div>
      </div>

      {/* Manual / Software Push-to-Talk Action Button */}
      <div className="pt-2 border-t border-slate-800/60">
        <button
          type="button"
          onMouseDown={onPttMouseDown}
          onMouseUp={onPttMouseUp}
          onTouchStart={onPttMouseDown}
          onTouchEnd={onPttMouseUp}
          className={`w-full py-3 px-4 rounded-xl font-bold tracking-wider text-sm flex items-center justify-center gap-2.5 transition-all select-none border ${
            levels.is_transmitting
              ? 'bg-rose-600 text-white border-rose-400 shadow-[0_0_25px_rgba(225,29,72,0.6)] scale-[0.99]'
              : 'bg-slate-800/80 hover:bg-slate-750 text-slate-200 border-slate-700/80 active:bg-slate-700'
          }`}
        >
          <Radio
            className={`w-5 h-5 ${levels.is_transmitting ? 'animate-spin' : 'text-slate-400'}`}
          />
          {levels.is_transmitting
            ? `TRANSMITTING ON ${activeRadioName} (RELEASE TO STOP)`
            : `PRESS & HOLD PTT TO TRANSMIT (${activeRadioName})`}
        </button>
      </div>
    </div>
  );
};
