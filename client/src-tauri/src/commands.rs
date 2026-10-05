use std::sync::Arc;
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;

use crate::ptt::{PttBinding, PttConfig, PttManager, RadioType};
use crate::xplane::{AircraftSnapshot, XPlaneUdpManager};

/// Active flight session information
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SessionInfo {
    pub callsign: String,
    pub aircraft_type: String,
}

impl Default for SessionInfo {
    fn default() -> Self {
        Self {
            callsign: "N172SP".to_string(),
            aircraft_type: "C172".to_string(),
        }
    }
}

/// VHF DSP filter and audio settings
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct DspSettings {
    pub noise_level: f32,
    pub squelch_volume: f32,
    pub bandpass_enabled: bool,
}

impl Default for DspSettings {
    fn default() -> Self {
        Self {
            noise_level: 0.03,
            squelch_volume: 0.8,
            bandpass_enabled: true,
        }
    }
}

/// Gateway connection status
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct GatewayInfo {
    pub url: String,
    pub connected: bool,
}

impl Default for GatewayInfo {
    fn default() -> Self {
        Self {
            url: "ws://127.0.0.1:8000/ws/audio".to_string(),
            connected: false,
        }
    }
}

/// Real-time audio VU meter payload emitted over Tauri IPC
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AudioLevelPayload {
    pub mic_level: f32,
    pub atc_level: f32,
    pub is_transmitting: bool,
}

/// Live transcript communications log entry
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct TranscriptEntry {
    pub id: String,
    pub timestamp: String,
    pub speaker: String,
    pub radio: String,
    pub text: String,
}

/// Shared application state managed by Tauri runtime
#[derive(Clone)]
pub struct AppState {
    pub xplane_manager: Arc<XPlaneUdpManager>,
    pub ptt_manager: Arc<PttManager>,
    pub session_info: Arc<RwLock<SessionInfo>>,
    pub dsp_settings: Arc<RwLock<DspSettings>>,
    pub gateway_info: Arc<RwLock<GatewayInfo>>,
}

impl AppState {
    pub fn new(xplane_manager: Arc<XPlaneUdpManager>, ptt_manager: Arc<PttManager>) -> Self {
        Self {
            xplane_manager,
            ptt_manager,
            session_info: Arc::new(RwLock::new(SessionInfo::default())),
            dsp_settings: Arc::new(RwLock::new(DspSettings::default())),
            gateway_info: Arc::new(RwLock::new(GatewayInfo::default())),
        }
    }

    pub async fn get_aircraft_state(&self) -> AircraftSnapshot {
        self.xplane_manager.get_snapshot().await
    }

    pub async fn set_callsign(&self, callsign: String, aircraft_type: String) -> SessionInfo {
        let mut session = self.session_info.write().await;
        session.callsign = callsign.trim().to_uppercase();
        session.aircraft_type = aircraft_type.trim().to_uppercase();
        session.clone()
    }

    pub fn set_ptt_binding(&self, radio: RadioType, binding: PttBinding) -> PttConfig {
        self.ptt_manager.set_binding(radio, binding);
        self.ptt_manager.get_config()
    }

    pub fn start_ptt_learning(&self, radio: RadioType) {
        self.ptt_manager.start_learn_mode(radio);
    }

    pub fn stop_ptt_learning(&self) {
        self.ptt_manager.stop_learn_mode();
    }

    pub fn get_ptt_config(&self) -> PttConfig {
        self.ptt_manager.get_config()
    }

    pub async fn set_dsp_settings(
        &self,
        noise_level: f32,
        squelch_volume: f32,
        bandpass_enabled: bool,
    ) -> DspSettings {
        let mut dsp = self.dsp_settings.write().await;
        dsp.noise_level = noise_level.clamp(0.0, 1.0);
        dsp.squelch_volume = squelch_volume.clamp(0.0, 1.0);
        dsp.bandpass_enabled = bandpass_enabled;
        dsp.clone()
    }

    pub async fn get_dsp_settings(&self) -> DspSettings {
        self.dsp_settings.read().await.clone()
    }

    pub async fn connect_gateway(&self, url: String) -> Result<GatewayInfo, String> {
        let trimmed = url.trim().to_string();
        if !trimmed.starts_with("ws://") && !trimmed.starts_with("wss://") {
            return Err(format!(
                "Invalid WebSocket URL schema: '{}'. Must start with ws:// or wss://",
                trimmed
            ));
        }

        let mut gw = self.gateway_info.write().await;
        gw.url = trimmed;
        gw.connected = true;
        Ok(gw.clone())
    }

    pub async fn get_session_info(&self) -> SessionInfo {
        self.session_info.read().await.clone()
    }

    pub fn trigger_ptt_press(&self, radio: RadioType) -> bool {
        self.ptt_manager.trigger_press(radio)
    }

    pub fn trigger_ptt_release(&self, radio: RadioType) -> bool {
        self.ptt_manager.trigger_release(radio)
    }
}

// Tauri v2 Command Handlers

#[tauri::command]
pub async fn get_aircraft_state(
    state: tauri::State<'_, AppState>,
) -> Result<AircraftSnapshot, String> {
    Ok(state.get_aircraft_state().await)
}

#[tauri::command]
pub async fn set_callsign(
    callsign: String,
    aircraft_type: String,
    state: tauri::State<'_, AppState>,
) -> Result<SessionInfo, String> {
    Ok(state.set_callsign(callsign, aircraft_type).await)
}

#[tauri::command]
pub fn set_ptt_binding(
    radio: RadioType,
    binding: PttBinding,
    state: tauri::State<'_, AppState>,
) -> Result<PttConfig, String> {
    Ok(state.set_ptt_binding(radio, binding))
}

#[tauri::command]
pub fn start_ptt_learning(
    radio: RadioType,
    state: tauri::State<'_, AppState>,
) -> Result<(), String> {
    state.start_ptt_learning(radio);
    Ok(())
}

#[tauri::command]
pub fn stop_ptt_learning(state: tauri::State<'_, AppState>) -> Result<(), String> {
    state.stop_ptt_learning();
    Ok(())
}

#[tauri::command]
pub fn get_ptt_config(state: tauri::State<'_, AppState>) -> Result<PttConfig, String> {
    Ok(state.get_ptt_config())
}

#[tauri::command]
pub async fn set_dsp_settings(
    noise_level: f32,
    squelch_volume: f32,
    bandpass_enabled: bool,
    state: tauri::State<'_, AppState>,
) -> Result<DspSettings, String> {
    Ok(state.set_dsp_settings(noise_level, squelch_volume, bandpass_enabled).await)
}

#[tauri::command]
pub async fn get_dsp_settings(state: tauri::State<'_, AppState>) -> Result<DspSettings, String> {
    Ok(state.get_dsp_settings().await)
}

#[tauri::command]
pub async fn connect_gateway(
    url: String,
    state: tauri::State<'_, AppState>,
) -> Result<GatewayInfo, String> {
    state.connect_gateway(url).await
}

#[tauri::command]
pub async fn get_session_info(state: tauri::State<'_, AppState>) -> Result<SessionInfo, String> {
    Ok(state.get_session_info().await)
}

#[tauri::command]
pub fn trigger_ptt_press(
    radio: RadioType,
    state: tauri::State<'_, AppState>,
) -> Result<bool, String> {
    Ok(state.trigger_ptt_press(radio))
}

#[tauri::command]
pub fn trigger_ptt_release(
    radio: RadioType,
    state: tauri::State<'_, AppState>,
) -> Result<bool, String> {
    Ok(state.trigger_ptt_release(radio))
}
