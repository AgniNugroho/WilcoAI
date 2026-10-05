use std::str::FromStr;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::Duration;

use global_hotkey::hotkey::{HotKey, HotKeyParseError};
use global_hotkey::{GlobalHotKeyEvent, GlobalHotKeyManager, HotKeyState};

use crate::ptt::{PttManager, RadioType};

#[cfg(windows)]
#[repr(C)]
struct WinMsg {
    hwnd: isize,
    message: u32,
    wparam: usize,
    lparam: isize,
    time: u32,
    pt_x: i32,
    pt_y: i32,
}

#[cfg(windows)]
extern "system" {
    fn PeekMessageW(
        msg: *mut WinMsg,
        hwnd: isize,
        filter_min: u32,
        filter_max: u32,
        remove_msg: u32,
    ) -> i32;
    fn TranslateMessage(msg: *const WinMsg) -> i32;
    fn DispatchMessageW(msg: *const WinMsg) -> isize;
}

/// Parses a string into a `HotKey` (e.g. "Space", "KeyT", "Control+Space", "Shift+KeyP")
pub fn parse_hotkey(s: &str) -> Result<HotKey, HotKeyParseError> {
    HotKey::from_str(s)
}

/// Background global hotkey listener that monitors system-wide keyboard shortcuts
pub struct HotkeyListener {
    running: Arc<AtomicBool>,
    manager: PttManager,
    thread_handle: Option<JoinHandle<()>>,
}

impl HotkeyListener {
    /// Create a new hotkey listener associated with a `PttManager`
    pub fn new(manager: PttManager) -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            manager,
            thread_handle: None,
        }
    }

    /// Returns whether the hotkey listener thread is running
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::Relaxed)
    }

    /// Starts monitoring registered global hotkeys in a background thread
    pub fn start(&mut self) {
        if self.is_running() {
            return;
        }

        self.running.store(true, Ordering::SeqCst);
        let running = Arc::clone(&self.running);
        let manager = self.manager.clone();

        let handle = thread::spawn(move || {
            let hotkey_mgr = match GlobalHotKeyManager::new() {
                Ok(mgr) => Some(mgr),
                Err(err) => {
                    eprintln!("Warning: Failed to initialize GlobalHotKeyManager: {:?}", err);
                    running.store(false, Ordering::SeqCst);
                    return;
                }
            };

            let mut active_com1: Option<HotKey> = None;
            let mut active_com2: Option<HotKey> = None;
            let mut last_com1_key: Option<String> = None;
            let mut last_com2_key: Option<String> = None;

            // Helper to sync registrations with current manager config only when string changes
            let sync_bindings = |mgr: &Option<GlobalHotKeyManager>,
                                 cur_com1: &mut Option<HotKey>,
                                 cur_com2: &mut Option<HotKey>,
                                 last_c1: &mut Option<String>,
                                 last_c2: &mut Option<String>| {
                if let Some(ref m) = mgr {
                    let cfg = manager.get_config();

                    // Update COM1 hotkey only if raw config string actually changed
                    if cfg.com1.keyboard_key != *last_c1 {
                        *last_c1 = cfg.com1.keyboard_key.clone();
                        if let Some(old) = cur_com1.take() {
                            let _ = m.unregister(old);
                        }
                        if let Some(ref key_str) = *last_c1 {
                            match parse_hotkey(key_str) {
                                Ok(new_hk) => {
                                    if let Err(err) = m.register(new_hk) {
                                        eprintln!("Warning: Failed to register COM1 hotkey '{}': {:?}", key_str, err);
                                    } else {
                                        *cur_com1 = Some(new_hk);
                                    }
                                }
                                Err(err) => {
                                    eprintln!("Warning: Invalid COM1 hotkey format '{}': {:?}", key_str, err);
                                }
                            }
                        }
                    }

                    // Update COM2 hotkey only if raw config string actually changed
                    if cfg.com2.keyboard_key != *last_c2 {
                        *last_c2 = cfg.com2.keyboard_key.clone();
                        if let Some(old) = cur_com2.take() {
                            let _ = m.unregister(old);
                        }
                        if let Some(ref key_str) = *last_c2 {
                            match parse_hotkey(key_str) {
                                Ok(new_hk) => {
                                    if let Err(err) = m.register(new_hk) {
                                        eprintln!("Warning: Failed to register COM2 hotkey '{}': {:?}", key_str, err);
                                    } else {
                                        *cur_com2 = Some(new_hk);
                                    }
                                }
                                Err(err) => {
                                    eprintln!("Warning: Invalid COM2 hotkey format '{}': {:?}", key_str, err);
                                }
                            }
                        }
                    }
                }
            };

            sync_bindings(&hotkey_mgr, &mut active_com1, &mut active_com2, &mut last_com1_key, &mut last_com2_key);

            let event_receiver = GlobalHotKeyEvent::receiver();

            while running.load(Ordering::Relaxed) {
                // Pump Windows messages on the listener thread to ensure WM_HOTKEY is dispatched
                #[cfg(windows)]
                unsafe {
                    let mut msg = std::mem::zeroed::<WinMsg>();
                    while PeekMessageW(&mut msg, 0, 0, 0, 1) != 0 {
                        TranslateMessage(&msg);
                        DispatchMessageW(&msg);
                    }
                }

                // Check for received hotkey events
                if let Ok(event) = event_receiver.recv_timeout(Duration::from_millis(15)) {
                    let id = event.id;
                    let is_pressed = event.state == HotKeyState::Pressed;

                    if let Some(ref com1) = active_com1 {
                        if com1.id() == id {
                            if is_pressed {
                                manager.trigger_press(RadioType::Com1);
                            } else {
                                manager.trigger_release(RadioType::Com1);
                            }
                            continue;
                        }
                    }

                    if let Some(ref com2) = active_com2 {
                        if com2.id() == id {
                            if is_pressed {
                                manager.trigger_press(RadioType::Com2);
                            } else {
                                manager.trigger_release(RadioType::Com2);
                            }
                            continue;
                        }
                    }
                }

                // Periodically sync bindings in case UI updated config
                sync_bindings(&hotkey_mgr, &mut active_com1, &mut active_com2, &mut last_com1_key, &mut last_com2_key);
            }

            // Cleanup registered hotkeys on shutdown
            if let Some(ref m) = hotkey_mgr {
                if let Some(hk) = active_com1 {
                    let _ = m.unregister(hk);
                }
                if let Some(hk) = active_com2 {
                    let _ = m.unregister(hk);
                }
            }

            running.store(false, Ordering::SeqCst);
        });

        self.thread_handle = Some(handle);
    }

    /// Stops the hotkey listener thread and waits for it to join
    pub fn stop(&mut self) {
        if self.running.swap(false, Ordering::SeqCst) {
            if let Some(handle) = self.thread_handle.take() {
                let _ = handle.join();
            }
        }
    }
}

impl Drop for HotkeyListener {
    fn drop(&mut self) {
        self.stop();
    }
}
