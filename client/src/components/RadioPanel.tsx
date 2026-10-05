import React from 'react';
import { Radio, Wifi, WifiOff, Plane, Wind } from 'lucide-react';
import { AircraftSnapshot } from '../types';

interface RadioPanelProps {
  snapshot: AircraftSnapshot;
  isSimConnected: boolean;
  onSelectRadio?: (radio: 1 | 2) => void;
}

// Frequency facility resolver helper
function getFacilityInfo(freqHz: number): { code: string; name: string; type: string; color: string } {
  const mhz = (freqHz / 1_000_000).toFixed(3);
  switch (mhz) {
    case '118.200':
      return { code: 'KSEA TWR', name: 'Seattle Tower', type: 'TWR', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' };
    case '121.700':
    case '121.900':
      return { code: 'KSEA GND', name: 'Seattle Ground', type: 'GND', color: 'bg-amber-500/20 text-amber-400 border-amber-500/40' };
    case '119.200':
    case '120.400':
      return { code: 'KSEA APP', name: 'Seattle Approach', type: 'APP', color: 'bg-sky-500/20 text-sky-400 border-sky-500/40' };
    case '128.000':
      return { code: 'KSEA DEP', name: 'Seattle Departure', type: 'DEP', color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40' };
    case '118.000':
      return { code: 'KSEA ATIS', name: 'Automatic Terminal Info', type: 'ATIS', color: 'bg-purple-500/20 text-purple-400 border-purple-500/40' };
    case '121.500':
      return { code: 'GUARD', name: 'Emergency Calling', type: 'EMG', color: 'bg-rose-500/20 text-rose-400 border-rose-500/40' };
    case '122.800':
      return { code: 'UNICOM', name: 'Common Traffic Advisory', type: 'CTAF', color: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40' };
    default:
      return { code: 'VHF COMM', name: 'Aviation Air-Ground', type: 'COM', color: 'bg-slate-700/40 text-slate-300 border-slate-600/40' };
  }
}

export const RadioPanel: React.FC<RadioPanelProps> = ({
  snapshot,
  isSimConnected,
  onSelectRadio,
}) => {
  const com1Mhz = (snapshot.com1_hz / 1_000_000).toFixed(3);
  const com2Mhz = (snapshot.com2_hz / 1_000_000).toFixed(3);

  const com1Facility = getFacilityInfo(snapshot.com1_hz);
  const com2Facility = getFacilityInfo(snapshot.com2_hz);

  const isCom1Active = snapshot.active_radio === 1;
  const isCom2Active = snapshot.active_radio === 2;

  const altitudeAglFt = Math.round(snapshot.agl_m * 3.28084);
  const altitudeMslFt = Math.round(snapshot.elevation_m * 3.28084);
  const groundspeedKts = Math.round(snapshot.groundspeed_ms * 1.94384);
  const windDirDeg = Math.round(snapshot.wind_dir);
  const windSpdKts = Math.round(snapshot.wind_speed);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col gap-5">
      {/* Header with Sim Connection Indicator */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <Radio className="w-5 h-5 text-emerald-400" />
          <span className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            VHF Radio Transceiver
          </span>
        </div>

        {/* Simulator Link Status */}
        <div className="flex items-center gap-2">
          {isSimConnected ? (
            <div className="flex items-center gap-2 bg-emerald-950/40 border border-emerald-500/30 px-3 py-1 rounded-full text-xs font-mono text-emerald-400">
              <Wifi className="w-3.5 h-3.5 animate-pulse text-emerald-400" />
              <span>X-PLANE 12 LINKED (10 Hz)</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 bg-amber-950/40 border border-amber-500/30 px-3 py-1 rounded-full text-xs font-mono text-amber-400">
              <WifiOff className="w-3.5 h-3.5 text-amber-400" />
              <span>WAITING FOR SIM (UDP 49000)</span>
            </div>
          )}
        </div>
      </div>

      {/* Dual Radio Displays */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* COM1 Box */}
        <div
          onClick={() => onSelectRadio && onSelectRadio(1)}
          className={`cursor-pointer relative p-4 rounded-xl border transition-all duration-200 ${
            isCom1Active
              ? 'bg-slate-950/90 border-emerald-500/50 shadow-[0_0_20px_rgba(16,185,129,0.12)]'
              : 'bg-slate-950/40 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold tracking-widest text-slate-400">COM1</span>
            <div className="flex items-center gap-1.5">
              {isCom1Active ? (
                <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  TRANSMIT ACTIVE
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider bg-slate-800/80 text-slate-400 border border-slate-700/50">
                  MONITOR
                </span>
              )}
            </div>
          </div>

          {/* Large Digital Frequency Readout */}
          <div className="font-mono text-3xl font-extrabold tracking-wider my-2 text-emerald-400 select-all drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]">
            {com1Mhz}
            <span className="text-xs text-emerald-500/70 ml-2 font-sans font-normal tracking-normal">
              MHz
            </span>
          </div>

          {/* Facility Identification Badge */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 mt-2">
            <span className="text-xs text-slate-400 truncate max-w-[150px]">
              {com1Facility.name}
            </span>
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded border ${com1Facility.color}`}
            >
              {com1Facility.code}
            </span>
          </div>
        </div>

        {/* COM2 Box */}
        <div
          onClick={() => onSelectRadio && onSelectRadio(2)}
          className={`cursor-pointer relative p-4 rounded-xl border transition-all duration-200 ${
            isCom2Active
              ? 'bg-slate-950/90 border-emerald-500/50 shadow-[0_0_20px_rgba(16,185,129,0.12)]'
              : 'bg-slate-950/40 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold tracking-widest text-slate-400">COM2</span>
            <div className="flex items-center gap-1.5">
              {isCom2Active ? (
                <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  TRANSMIT ACTIVE
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider bg-slate-800/80 text-slate-400 border border-slate-700/50">
                  MONITOR
                </span>
              )}
            </div>
          </div>

          {/* Large Digital Frequency Readout */}
          <div className="font-mono text-3xl font-extrabold tracking-wider my-2 text-cyan-400 select-all drop-shadow-[0_0_8px_rgba(6,182,212,0.3)]">
            {com2Mhz}
            <span className="text-xs text-cyan-500/70 ml-2 font-sans font-normal tracking-normal">
              MHz
            </span>
          </div>

          {/* Facility Identification Badge */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 mt-2">
            <span className="text-xs text-slate-400 truncate max-w-[150px]">
              {com2Facility.name}
            </span>
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded border ${com2Facility.color}`}
            >
              {com2Facility.code}
            </span>
          </div>
        </div>
      </div>

      {/* Flight Telemetry Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 border-t border-slate-800/80 text-xs font-mono">
        {/* Squawk */}
        <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60 flex flex-col gap-1">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">XPDR Squawk</span>
          <div className="flex items-center justify-between">
            <span className="font-bold text-amber-400 text-sm">
              {snapshot.squawk.toString().padStart(4, '0')}
            </span>
            <span className="text-[10px] px-1.5 py-0.2 bg-slate-800 text-slate-300 rounded font-sans">
              ALT
            </span>
          </div>
        </div>

        {/* Altimeter QNH */}
        <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60 flex flex-col gap-1">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Altimeter (QNH)</span>
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-200 text-sm">
              {snapshot.qnh_inhg.toFixed(2)}
            </span>
            <span className="text-[10px] text-slate-400 font-sans">inHg</span>
          </div>
        </div>

        {/* Altitude / Groundspeed */}
        <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60 flex flex-col gap-1">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider flex items-center gap-1">
            <Plane className="w-3 h-3 text-cyan-400" />
            Alt / Speed
          </span>
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-200 text-sm">
              {altitudeAglFt} <span className="text-[10px] text-slate-400 font-normal">AGL</span>
              <span className="text-[10px] text-slate-500 font-normal ml-1">({altitudeMslFt} MSL)</span>
            </span>
            <span className="text-xs text-emerald-400 font-bold">
              {groundspeedKts} <span className="text-[10px] font-normal text-slate-400">kt</span>
            </span>
          </div>
        </div>

        {/* Wind */}
        <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/60 flex flex-col gap-1">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider flex items-center gap-1">
            <Wind className="w-3 h-3 text-sky-400" />
            Wind Layer
          </span>
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-200 text-sm">
              {windDirDeg}° / {windSpdKts} kt
            </span>
            <span
              className={`text-[9px] px-1 py-0.5 rounded font-sans uppercase font-bold ${
                snapshot.on_ground
                  ? 'bg-amber-950 text-amber-400 border border-amber-800/50'
                  : 'bg-sky-950 text-sky-400 border border-sky-800/50'
              }`}
            >
              {snapshot.on_ground ? 'GND' : 'AIR'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
