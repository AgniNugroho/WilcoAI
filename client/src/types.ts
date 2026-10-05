export type RadioType = 'Com1' | 'Com2';

export interface PttBinding {
  joystick_button?: number | null;
  keyboard_key?: string | null;
  mouse_button?: number | null;
}

export interface PttConfig {
  com1: PttBinding;
  com2: PttBinding;
}

export interface AircraftSnapshot {
  com1_hz: number;
  com2_hz: number;
  active_radio: number; // 1 = COM1, 2 = COM2
  lat: number;
  lon: number;
  elevation_m: number;
  agl_m: number;
  on_ground: boolean;
  squawk: number;
  qnh_inhg: number;
  groundspeed_ms: number;
  wind_speed: number;
  wind_dir: number;
}

export interface SessionInfo {
  callsign: string;
  aircraft_type: string;
}

export interface DspSettings {
  noise_level: number;
  squelch_volume: number;
  bandpass_enabled: boolean;
}

export interface GatewayInfo {
  url: string;
  connected: boolean;
}

export interface AudioLevelPayload {
  mic_level: number;
  atc_level: number;
  is_transmitting: boolean;
}

export type SpeakerType = 'Pilot' | 'ATC' | 'ATIS';

export interface TranscriptEntry {
  id: string;
  timestamp: string;
  speaker: SpeakerType;
  radio: 'COM1' | 'COM2';
  text: string;
  clearanceType?: string;
}
