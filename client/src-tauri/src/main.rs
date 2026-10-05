// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Arc;
use std::time::Duration;
use tauri::{Emitter, Manager};
use wilco_client::commands::{self, AppState, AudioLevelPayload};
use wilco_client::ptt::PttManager;
use wilco_client::xplane::XPlaneUdpManager;

fn main() {
    let xplane_manager = Arc::new(
        XPlaneUdpManager::default_local()
            .unwrap_or_else(|e| panic!("Failed to bind local X-Plane UDP socket: {e}")),
    );
    let ptt_manager = Arc::new(PttManager::new());
    let app_state = AppState::new(xplane_manager.clone(), ptt_manager.clone());

    tauri::Builder::default()
        .manage(app_state)
        .setup(|app| {
            let handle = app.handle().clone();
            let ptt_mgr = handle.state::<AppState>().ptt_manager.clone();
            let xp_mgr = handle.state::<AppState>().xplane_manager.clone();

            // Spawn X-Plane UDP listener background receiver
            xp_mgr.clone().spawn_background();

            // Background task: forward PTT events to webview with lag recovery
            let handle_ptt = handle.clone();
            let mut ptt_rx = ptt_mgr.subscribe();
            tauri::async_runtime::spawn(async move {
                loop {
                    match ptt_rx.recv().await {
                        Ok(evt) => {
                            let _ = handle_ptt.emit("ptt_state_change", &evt);
                        }
                        Err(tokio::sync::broadcast::error::RecvError::Lagged(skipped)) => {
                            eprintln!("Warning: PTT broadcast receiver lagged by {skipped} messages");
                            continue;
                        }
                        Err(tokio::sync::broadcast::error::RecvError::Closed) => {
                            break;
                        }
                    }
                }
            });

            // Background task: monitor PTT learning mode and binding updates
            let handle_config = handle.clone();
            let ptt_mgr_cfg = ptt_mgr.clone();
            tauri::async_runtime::spawn(async move {
                let mut interval = tokio::time::interval(Duration::from_millis(50));
                let mut last_cfg = ptt_mgr_cfg.get_config();
                let mut was_learning = ptt_mgr_cfg.is_learning().is_some();

                loop {
                    interval.tick().await;
                    let current_cfg = ptt_mgr_cfg.get_config();
                    let is_learning = ptt_mgr_cfg.is_learning().is_some();

                    if current_cfg != last_cfg || (was_learning && !is_learning) {
                        last_cfg = current_cfg.clone();
                        let _ = handle_config.emit("ptt_config_updated", &current_cfg);
                    }
                    was_learning = is_learning;
                }
            });

            // Background task: periodic telemetry and audio levels emission (10 Hz)
            let handle_telemetry = handle.clone();
            tauri::async_runtime::spawn(async move {
                let mut interval = tokio::time::interval(Duration::from_millis(100));
                let mut tx_phase: f32 = 0.0;
                loop {
                    interval.tick().await;

                    // 1. Telemetry update
                    let snapshot = xp_mgr.get_snapshot().await;
                    let _ = handle_telemetry.emit("telemetry_update", &snapshot);

                    // 2. Audio level update
                    let is_transmitting = ptt_mgr.state().is_transmitting();
                    let mic_level = if is_transmitting {
                        tx_phase += 0.4;
                        (0.5 + 0.3 * tx_phase.sin()).clamp(0.1, 0.95)
                    } else {
                        0.0
                    };

                    let audio_payload = AudioLevelPayload {
                        mic_level,
                        atc_level: 0.0,
                        is_transmitting,
                    };
                    let _ = handle_telemetry.emit("audio_level_update", &audio_payload);
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_aircraft_state,
            commands::set_callsign,
            commands::set_ptt_binding,
            commands::start_ptt_learning,
            commands::stop_ptt_learning,
            commands::get_ptt_config,
            commands::set_dsp_settings,
            commands::get_dsp_settings,
            commands::connect_gateway,
            commands::get_session_info,
            commands::trigger_ptt_press,
            commands::trigger_ptt_release,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
