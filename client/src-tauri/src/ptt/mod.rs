pub mod hotkey;
pub mod joystick;

use std::fmt;
use std::sync::{Arc, RwLock};
use serde::{Deserialize, Serialize};
use tokio::sync::broadcast;

pub use hotkey::{parse_hotkey, HotkeyListener};
pub use joystick::JoystickListener;

/// Radio selection for Push-To-Talk transmission
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RadioType {
    Com1,
    Com2,
}

impl fmt::Display for RadioType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RadioType::Com1 => write!(f, "COM1"),
            RadioType::Com2 => write!(f, "COM2"),
        }
    }
}

/// Push-To-Talk transmission state machine states
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum PttState {
    #[default]
    Idle,
    Transmitting(RadioType),
}

impl PttState {
    /// Returns true if currently transmitting on any radio
    pub fn is_transmitting(&self) -> bool {
        matches!(self, Self::Transmitting(_))
    }

    /// Returns the active radio if transmitting, or None if idle
    pub fn active_radio(&self) -> Option<RadioType> {
        match self {
            Self::Transmitting(radio) => Some(*radio),
            Self::Idle => None,
        }
    }
}

/// Push-To-Talk broadcast events emitted on transitions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PttEvent {
    Pressed { radio: RadioType },
    Released { radio: RadioType },
}

impl PttEvent {
    /// Returns the target radio associated with this event
    pub fn radio(&self) -> RadioType {
        match *self {
            Self::Pressed { radio } | Self::Released { radio } => radio,
        }
    }

    /// Returns true if this is a Pressed event
    pub fn is_pressed(&self) -> bool {
        matches!(self, Self::Pressed { .. })
    }

    /// Returns true if this is a Released event
    pub fn is_released(&self) -> bool {
        matches!(self, Self::Released { .. })
    }
}

/// Input binding configuration for a single radio
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct PttBinding {
    /// USB Joystick / flight yoke hardware button index or code
    pub joystick_button: Option<u32>,
    /// Global keyboard hotkey description (e.g. "Space", "KeyT", "Control+Space")
    pub keyboard_key: Option<String>,
}

impl PttBinding {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn from_joystick(button: u32) -> Self {
        Self {
            joystick_button: Some(button),
            keyboard_key: None,
        }
    }

    pub fn from_keyboard(key: impl Into<String>) -> Self {
        Self {
            joystick_button: None,
            keyboard_key: Some(key.into()),
        }
    }

    pub fn with_joystick(mut self, button: u32) -> Self {
        self.joystick_button = Some(button);
        self
    }

    pub fn with_keyboard(mut self, key: impl Into<String>) -> Self {
        self.keyboard_key = Some(key.into());
        self
    }

    pub fn matches_joystick(&self, button: u32) -> bool {
        self.joystick_button == Some(button)
    }

    pub fn matches_keyboard(&self, key: &str) -> bool {
        self.keyboard_key.as_deref() == Some(key)
    }

    pub fn is_empty(&self) -> bool {
        self.joystick_button.is_none() && self.keyboard_key.is_none()
    }
}

/// Complete dual-radio PTT binding configuration
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct PttConfig {
    pub com1: PttBinding,
    pub com2: PttBinding,
}

/// Thread-safe controller managing global PTT state, hardware polling, and key learning
#[derive(Clone)]
pub struct PttManager {
    state: Arc<RwLock<PttState>>,
    config: Arc<RwLock<PttConfig>>,
    learn_target: Arc<RwLock<Option<RadioType>>>,
    event_tx: broadcast::Sender<PttEvent>,
}

impl Default for PttManager {
    fn default() -> Self {
        Self::new()
    }
}

impl PttManager {
    /// Creates a new PttManager initialized to Idle state with empty bindings
    pub fn new() -> Self {
        let (event_tx, _) = broadcast::channel(64);
        Self {
            state: Arc::new(RwLock::new(PttState::Idle)),
            config: Arc::new(RwLock::new(PttConfig::default())),
            learn_target: Arc::new(RwLock::new(None)),
            event_tx,
        }
    }

    /// Creates a new PttManager with preconfigured bindings
    pub fn with_config(config: PttConfig) -> Self {
        let (event_tx, _) = broadcast::channel(64);
        Self {
            state: Arc::new(RwLock::new(PttState::Idle)),
            config: Arc::new(RwLock::new(config)),
            learn_target: Arc::new(RwLock::new(None)),
            event_tx,
        }
    }

    /// Returns the current PttState (Idle or Transmitting(RadioType))
    pub fn state(&self) -> PttState {
        *self.state.read().unwrap()
    }

    /// Subscribes to the broadcast stream of PTT transition events
    pub fn subscribe(&self) -> broadcast::Receiver<PttEvent> {
        self.event_tx.subscribe()
    }

    /// Programmatically triggers PTT press for the given radio.
    /// Returns true if state transitioned, false if already transmitting on that radio.
    pub fn trigger_press(&self, radio: RadioType) -> bool {
        let mut state = self.state.write().unwrap();
        if *state != PttState::Transmitting(radio) {
            *state = PttState::Transmitting(radio);
            let _ = self.event_tx.send(PttEvent::Pressed { radio });
            true
        } else {
            false
        }
    }

    /// Programmatically triggers PTT release for the given radio.
    /// Returns true if state transitioned to Idle, false if wasn't transmitting on that radio.
    pub fn trigger_release(&self, radio: RadioType) -> bool {
        let mut state = self.state.write().unwrap();
        if *state == PttState::Transmitting(radio) {
            *state = PttState::Idle;
            let _ = self.event_tx.send(PttEvent::Released { radio });
            true
        } else {
            false
        }
    }

    /// Resets the transmitter state to Idle unconditionally
    pub fn reset(&self) {
        let mut state = self.state.write().unwrap();
        if let PttState::Transmitting(radio) = *state {
            *state = PttState::Idle;
            let _ = self.event_tx.send(PttEvent::Released { radio });
        }
    }

    /// Enters button/key learning mode for the given radio
    pub fn start_learn_mode(&self, radio: RadioType) {
        let mut target = self.learn_target.write().unwrap();
        *target = Some(radio);
    }

    /// Cancels button/key learning mode
    pub fn stop_learn_mode(&self) {
        let mut target = self.learn_target.write().unwrap();
        *target = None;
    }

    /// Returns which radio is currently in learn mode, or None if not learning
    pub fn is_learning(&self) -> Option<RadioType> {
        *self.learn_target.read().unwrap()
    }

    /// Retrieves current binding configuration for a specific radio
    pub fn get_binding(&self, radio: RadioType) -> PttBinding {
        let cfg = self.config.read().unwrap();
        match radio {
            RadioType::Com1 => cfg.com1.clone(),
            RadioType::Com2 => cfg.com2.clone(),
        }
    }

    /// Sets binding configuration for a specific radio
    pub fn set_binding(&self, radio: RadioType, binding: PttBinding) {
        let mut cfg = self.config.write().unwrap();
        match radio {
            RadioType::Com1 => cfg.com1 = binding,
            RadioType::Com2 => cfg.com2 = binding,
        }
    }

    /// Returns a copy of the full dual-radio configuration
    pub fn get_config(&self) -> PttConfig {
        self.config.read().unwrap().clone()
    }

    /// Updates the full dual-radio configuration
    pub fn set_config(&self, config: PttConfig) {
        let mut cfg = self.config.write().unwrap();
        *cfg = config;
    }

    /// Handles joystick / gamepad button press event
    pub fn handle_joystick_press(&self, button: u32) {
        // If learning mode is active, bind this button to the target radio
        if let Some(target) = self.is_learning() {
            {
                let mut cfg = self.config.write().unwrap();
                match target {
                    RadioType::Com1 => cfg.com1.joystick_button = Some(button),
                    RadioType::Com2 => cfg.com2.joystick_button = Some(button),
                }
            }
            self.stop_learn_mode();
            return;
        }

        // Otherwise check registered bindings
        let cfg = self.config.read().unwrap();
        if cfg.com1.matches_joystick(button) {
            drop(cfg);
            self.trigger_press(RadioType::Com1);
        } else if cfg.com2.matches_joystick(button) {
            drop(cfg);
            self.trigger_press(RadioType::Com2);
        }
    }

    /// Handles joystick / gamepad button release event
    pub fn handle_joystick_release(&self, button: u32) {
        if self.is_learning().is_some() {
            return;
        }

        let cfg = self.config.read().unwrap();
        if cfg.com1.matches_joystick(button) {
            drop(cfg);
            self.trigger_release(RadioType::Com1);
        } else if cfg.com2.matches_joystick(button) {
            drop(cfg);
            self.trigger_release(RadioType::Com2);
        }
    }

    /// Handles keyboard key press event
    pub fn handle_keyboard_press(&self, key: &str) {
        // If learning mode is active, bind this key to the target radio
        if let Some(target) = self.is_learning() {
            {
                let mut cfg = self.config.write().unwrap();
                match target {
                    RadioType::Com1 => cfg.com1.keyboard_key = Some(key.to_string()),
                    RadioType::Com2 => cfg.com2.keyboard_key = Some(key.to_string()),
                }
            }
            self.stop_learn_mode();
            return;
        }

        // Otherwise check registered bindings
        let cfg = self.config.read().unwrap();
        if cfg.com1.matches_keyboard(key) {
            drop(cfg);
            self.trigger_press(RadioType::Com1);
        } else if cfg.com2.matches_keyboard(key) {
            drop(cfg);
            self.trigger_press(RadioType::Com2);
        }
    }

    /// Handles keyboard key release event
    pub fn handle_keyboard_release(&self, key: &str) {
        if self.is_learning().is_some() {
            return;
        }

        let cfg = self.config.read().unwrap();
        if cfg.com1.matches_keyboard(key) {
            drop(cfg);
            self.trigger_release(RadioType::Com1);
        } else if cfg.com2.matches_keyboard(key) {
            drop(cfg);
            self.trigger_release(RadioType::Com2);
        }
    }
}
