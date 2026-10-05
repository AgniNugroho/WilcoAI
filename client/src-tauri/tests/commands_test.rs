use std::sync::Arc;
use wilco_client::commands::{AppState, DspSettings, GatewayInfo, SessionInfo};
use wilco_client::ptt::{PttBinding, PttManager, RadioType};
use wilco_client::xplane::XPlaneUdpManager;

#[tokio::test]
async fn test_app_state_initialization_and_snapshot() {
    let xp = Arc::new(XPlaneUdpManager::default_local().expect("UDP manager init"));
    let ptt = Arc::new(PttManager::new());
    let state = AppState::new(xp, ptt);

    let snap = state.get_aircraft_state().await;
    assert_eq!(snap.com1_hz, 118_200_000);
    assert_eq!(snap.com2_hz, 121_650_000);
    assert_eq!(snap.active_radio, 1);
}

#[tokio::test]
async fn test_set_callsign_and_session_info() {
    let xp = Arc::new(XPlaneUdpManager::default_local().expect("UDP manager init"));
    let ptt = Arc::new(PttManager::new());
    let state = AppState::new(xp, ptt);

    let default_sess = state.get_session_info().await;
    assert_eq!(default_sess.callsign, "N172SP");
    assert_eq!(default_sess.aircraft_type, "C172");

    let updated = state.set_callsign("dal452".to_string(), "b738".to_string()).await;
    assert_eq!(updated.callsign, "DAL452");
    assert_eq!(updated.aircraft_type, "B738");

    let retrieved = state.get_session_info().await;
    assert_eq!(retrieved, updated);
}

#[tokio::test]
async fn test_ptt_binding_and_learning_lifecycle() {
    let xp = Arc::new(XPlaneUdpManager::default_local().expect("UDP manager init"));
    let ptt = Arc::new(PttManager::new());
    let state = AppState::new(xp, ptt.clone());

    // Set COM1 binding to joystick button 1
    let binding = PttBinding::from_joystick(1);
    let cfg = state.set_ptt_binding(RadioType::Com1, binding);
    assert_eq!(cfg.com1.joystick_button, Some(1));
    assert_eq!(state.get_ptt_config().com1.joystick_button, Some(1));

    // Learning mode start & stop
    assert_eq!(ptt.is_learning(), None);
    state.start_ptt_learning(RadioType::Com2);
    assert_eq!(ptt.is_learning(), Some(RadioType::Com2));
    state.stop_ptt_learning();
    assert_eq!(ptt.is_learning(), None);
}

#[tokio::test]
async fn test_dsp_settings_and_clamping() {
    let xp = Arc::new(XPlaneUdpManager::default_local().expect("UDP manager init"));
    let ptt = Arc::new(PttManager::new());
    let state = AppState::new(xp, ptt);

    let default_dsp = state.get_dsp_settings().await;
    assert!(default_dsp.bandpass_enabled);

    // Test clamped values (negative noise clamped to 0.0, excess volume clamped to 1.0)
    let updated = state.set_dsp_settings(-0.5, 1.5, false).await;
    assert_eq!(updated.noise_level, 0.0);
    assert_eq!(updated.squelch_volume, 1.0);
    assert!(!updated.bandpass_enabled);

    let retrieved = state.get_dsp_settings().await;
    assert_eq!(retrieved, updated);
}

#[tokio::test]
async fn test_connect_gateway_validation() {
    let xp = Arc::new(XPlaneUdpManager::default_local().expect("UDP manager init"));
    let ptt = Arc::new(PttManager::new());
    let state = AppState::new(xp, ptt);

    // Invalid schema
    let err_res = state.connect_gateway("http://localhost:8000".to_string()).await;
    assert!(err_res.is_err());
    assert!(err_res.unwrap_err().contains("Invalid WebSocket URL schema"));

    // Valid ws:// schema
    let ok_res = state.connect_gateway("ws://127.0.0.1:8000/ws/audio".to_string()).await;
    assert!(ok_res.is_ok());
    let gw = ok_res.unwrap();
    assert_eq!(gw.url, "ws://127.0.0.1:8000/ws/audio");
    assert_eq!(gw.connected, true);

    // Valid wss:// schema
    let wss_res = state.connect_gateway("wss://gateway.wilcoai.com/ws".to_string()).await;
    assert!(wss_res.is_ok());
    assert_eq!(wss_res.unwrap().connected, true);
}

#[tokio::test]
async fn test_ptt_programmatic_trigger() {
    let xp = Arc::new(XPlaneUdpManager::default_local().expect("UDP manager init"));
    let ptt = Arc::new(PttManager::new());
    let state = AppState::new(xp, ptt.clone());

    assert!(!ptt.state().is_transmitting());
    let pressed = state.trigger_ptt_press(RadioType::Com1);
    assert!(pressed);
    assert!(ptt.state().is_transmitting());
    assert_eq!(ptt.state().active_radio(), Some(RadioType::Com1));

    let released = state.trigger_ptt_release(RadioType::Com1);
    assert!(released);
    assert!(!ptt.state().is_transmitting());
}
