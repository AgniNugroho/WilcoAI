use wilco_client::ptt::{
    hotkey::HotkeyListener,
    joystick::JoystickListener,
    PttBinding, PttConfig, PttEvent, PttManager, PttState, RadioType,
};

#[test]
fn test_initial_state_is_idle() {
    let manager = PttManager::new();
    assert_eq!(manager.state(), PttState::Idle);
    assert!(!manager.state().is_transmitting());
    assert_eq!(manager.state().active_radio(), None);
}

#[tokio::test]
async fn test_trigger_com1_press_and_release() {
    let manager = PttManager::new();
    let mut rx = manager.subscribe();

    // Trigger Press on COM1
    let changed = manager.trigger_press(RadioType::Com1);
    assert!(changed);
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com1));
    assert!(manager.state().is_transmitting());
    assert_eq!(manager.state().active_radio(), Some(RadioType::Com1));

    let event = rx.recv().await.expect("Failed to receive PTT event");
    assert_eq!(event, PttEvent::Pressed { radio: RadioType::Com1 });
    assert!(event.is_pressed());
    assert_eq!(event.radio(), RadioType::Com1);

    // Trigger Release on COM1
    let changed = manager.trigger_release(RadioType::Com1);
    assert!(changed);
    assert_eq!(manager.state(), PttState::Idle);
    assert!(!manager.state().is_transmitting());
    assert_eq!(manager.state().active_radio(), None);

    let event = rx.recv().await.expect("Failed to receive PTT event");
    assert_eq!(event, PttEvent::Released { radio: RadioType::Com1 });
    assert!(event.is_released());
    assert_eq!(event.radio(), RadioType::Com1);
}

#[tokio::test]
async fn test_trigger_com2_press_and_release() {
    let manager = PttManager::new();
    let mut rx = manager.subscribe();

    // Trigger Press on COM2
    let changed = manager.trigger_press(RadioType::Com2);
    assert!(changed);
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com2));
    assert_eq!(manager.state().active_radio(), Some(RadioType::Com2));

    let event = rx.recv().await.expect("Failed to receive PTT event");
    assert_eq!(event, PttEvent::Pressed { radio: RadioType::Com2 });

    // Trigger Release on COM2
    let changed = manager.trigger_release(RadioType::Com2);
    assert!(changed);
    assert_eq!(manager.state(), PttState::Idle);

    let event = rx.recv().await.expect("Failed to receive PTT event");
    assert_eq!(event, PttEvent::Released { radio: RadioType::Com2 });
}

#[tokio::test]
async fn test_idempotent_press_and_mismatched_release() {
    let manager = PttManager::new();
    let mut rx = manager.subscribe();

    // First press COM1 -> transitions
    assert!(manager.trigger_press(RadioType::Com1));
    let _ = rx.recv().await.unwrap();

    // Duplicate press COM1 -> no-op
    assert!(!manager.trigger_press(RadioType::Com1));
    assert!(rx.try_recv().is_err());

    // Release COM2 while transmitting COM1 -> ignored, state remains COM1
    assert!(!manager.trigger_release(RadioType::Com2));
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com1));
    assert!(rx.try_recv().is_err());

    // Proper release COM1 -> transitions to Idle
    assert!(manager.trigger_release(RadioType::Com1));
    assert_eq!(manager.state(), PttState::Idle);
    let event = rx.recv().await.unwrap();
    assert_eq!(event, PttEvent::Released { radio: RadioType::Com1 });

    // Duplicate release COM1 -> no-op
    assert!(!manager.trigger_release(RadioType::Com1));
    assert!(rx.try_recv().is_err());
}

#[tokio::test]
async fn test_learning_mode_joystick() {
    let manager = PttManager::new();
    let mut rx = manager.subscribe();

    assert_eq!(manager.is_learning(), None);
    assert_eq!(manager.get_binding(RadioType::Com1).joystick_button, None);

    // Enter learn mode for COM1
    manager.start_learn_mode(RadioType::Com1);
    assert_eq!(manager.is_learning(), Some(RadioType::Com1));

    // Simulate joystick hardware button 14 press
    manager.handle_joystick_press(14);

    // Learn mode should have completed and stored the binding
    assert_eq!(manager.is_learning(), None);
    assert_eq!(manager.get_binding(RadioType::Com1).joystick_button, Some(14));
    assert_eq!(manager.state(), PttState::Idle);
    // Learn event should not have triggered audio transmission
    assert!(rx.try_recv().is_err());

    // Now, actual press on mapped button 14 should key COM1
    manager.handle_joystick_press(14);
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com1));
    let event = rx.recv().await.unwrap();
    assert_eq!(event, PttEvent::Pressed { radio: RadioType::Com1 });

    // Release button 14 should unkey COM1
    manager.handle_joystick_release(14);
    assert_eq!(manager.state(), PttState::Idle);
    let event = rx.recv().await.unwrap();
    assert_eq!(event, PttEvent::Released { radio: RadioType::Com1 });
}

#[tokio::test]
async fn test_learning_mode_keyboard() {
    let manager = PttManager::new();
    let mut rx = manager.subscribe();

    assert_eq!(manager.is_learning(), None);
    assert_eq!(manager.get_binding(RadioType::Com2).keyboard_key, None);

    // Enter learn mode for COM2
    manager.start_learn_mode(RadioType::Com2);
    assert_eq!(manager.is_learning(), Some(RadioType::Com2));

    // Simulate keyboard press "KeyT"
    manager.handle_keyboard_press("KeyT");

    // Learn mode should complete and store binding
    assert_eq!(manager.is_learning(), None);
    assert_eq!(
        manager.get_binding(RadioType::Com2).keyboard_key.as_deref(),
        Some("KeyT")
    );
    assert_eq!(manager.state(), PttState::Idle);
    assert!(rx.try_recv().is_err());

    // Press "KeyT" keys COM2
    manager.handle_keyboard_press("KeyT");
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com2));
    let event = rx.recv().await.unwrap();
    assert_eq!(event, PttEvent::Pressed { radio: RadioType::Com2 });

    // Release "KeyT" unkeys COM2
    manager.handle_keyboard_release("KeyT");
    assert_eq!(manager.state(), PttState::Idle);
    let event = rx.recv().await.unwrap();
    assert_eq!(event, PttEvent::Released { radio: RadioType::Com2 });
}

#[test]
fn test_ptt_types_serde_json() {
    let binding = PttBinding {
        joystick_button: Some(3),
        keyboard_key: Some("Space".into()),
    };
    let json = serde_json::to_string(&binding).expect("serialize binding");
    let deser: PttBinding = serde_json::from_str(&json).expect("deserialize binding");
    assert_eq!(deser, binding);

    let config = PttConfig {
        com1: binding.clone(),
        com2: PttBinding::from_joystick(7),
    };
    let cfg_json = serde_json::to_string(&config).expect("serialize config");
    let deser_cfg: PttConfig = serde_json::from_str(&cfg_json).expect("deserialize config");
    assert_eq!(deser_cfg, config);

    let event = PttEvent::Pressed { radio: RadioType::Com1 };
    let ev_json = serde_json::to_string(&event).expect("serialize event");
    let deser_ev: PttEvent = serde_json::from_str(&ev_json).expect("deserialize event");
    assert_eq!(deser_ev, event);

    let state = PttState::Transmitting(RadioType::Com2);
    let st_json = serde_json::to_string(&state).expect("serialize state");
    let deser_st: PttState = serde_json::from_str(&st_json).expect("deserialize state");
    assert_eq!(deser_st, state);
}

#[test]
fn test_hardware_listeners_instantiation_mock() {
    let manager = PttManager::new();

    // Verify JoystickListener creation/stop without physical hardware
    let mut joystick = JoystickListener::new(manager.clone());
    assert!(!joystick.is_running());
    joystick.stop();

    // Verify HotkeyListener creation/stop
    let mut hotkey = HotkeyListener::new(manager.clone());
    assert!(!hotkey.is_running());
    hotkey.stop();
}

#[tokio::test]
async fn test_radio_switch_emits_released_then_pressed() {
    let manager = PttManager::new();
    let mut rx = manager.subscribe();

    // 1. Initial press on COM1
    assert!(manager.trigger_press(RadioType::Com1));
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com1));
    let ev1 = rx.recv().await.expect("recv Com1 press");
    assert_eq!(ev1, PttEvent::Pressed { radio: RadioType::Com1 });

    // 2. Direct switch to COM2 while COM1 is transmitting:
    // Must emit Released for COM1 before Pressed for COM2
    assert!(manager.trigger_press(RadioType::Com2));
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com2));

    let ev2 = rx.recv().await.expect("recv Com1 release on switch");
    assert_eq!(ev2, PttEvent::Released { radio: RadioType::Com1 });

    let ev3 = rx.recv().await.expect("recv Com2 press on switch");
    assert_eq!(ev3, PttEvent::Pressed { radio: RadioType::Com2 });

    // 3. Switch back to COM1 while COM2 is transmitting:
    // Must emit Released for COM2 before Pressed for COM1
    assert!(manager.trigger_press(RadioType::Com1));
    assert_eq!(manager.state(), PttState::Transmitting(RadioType::Com1));

    let ev4 = rx.recv().await.expect("recv Com2 release on switch");
    assert_eq!(ev4, PttEvent::Released { radio: RadioType::Com2 });

    let ev5 = rx.recv().await.expect("recv Com1 press on switch");
    assert_eq!(ev5, PttEvent::Pressed { radio: RadioType::Com1 });

    // 4. Release COM1 returns to Idle
    assert!(manager.trigger_release(RadioType::Com1));
    assert_eq!(manager.state(), PttState::Idle);

    let ev6 = rx.recv().await.expect("recv final Com1 release");
    assert_eq!(ev6, PttEvent::Released { radio: RadioType::Com1 });
}

#[test]
fn test_learning_mode_atomic_single_consumer() {
    let manager = PttManager::new();

    manager.start_learn_mode(RadioType::Com1);
    assert_eq!(manager.is_learning(), Some(RadioType::Com1));

    // First button press consumes the learn target atomically
    manager.handle_joystick_press(5);
    assert_eq!(manager.is_learning(), None);
    assert_eq!(manager.get_binding(RadioType::Com1).joystick_button, Some(5));

    // A second rapid button press should NOT overwrite the binding because learning was consumed
    manager.handle_joystick_press(9);
    assert_eq!(manager.get_binding(RadioType::Com1).joystick_button, Some(5));
}

