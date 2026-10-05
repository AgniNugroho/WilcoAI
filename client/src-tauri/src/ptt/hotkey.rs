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
                    None
                }
            };

            let mut active_com1: Option<HotKey> = None;
            let mut active_com2: Option<HotKey> = None;

            // Helper to sync registrations with current manager config
            let sync_bindings = |mgr: &Option<GlobalHotKeyManager>,
                                 cur_com1: &mut Option<HotKey>,
                                 cur_com2: &mut Option<HotKey>| {
                if let Some(ref m) = mgr {
                    let cfg = manager.get_config();

                    // Update COM1 hotkey
                    let new_com1 = cfg.com1.keyboard_key.as_deref().and_then(|k| parse_hotkey(k).ok());
                    if new_com1 != *cur_com1 {
                        if let Some(old) = cur_com1.take() {
                            let _ = m.unregister(old);
                        }
                        if let Some(new_hk) = new_com1 {
                            if m.register(new_hk).is_ok() {
                                *cur_com1 = Some(new_hk);
                            }
                        }
                    }

                    // Update COM2 hotkey
                    let new_com2 = cfg.com2.keyboard_key.as_deref().and_then(|k| parse_hotkey(k).ok());
                    if new_com2 != *cur_com2 {
                        if let Some(old) = cur_com2.take() {
                            let _ = m.unregister(old);
                        }
                        if let Some(new_hk) = new_com2 {
                            if m.register(new_hk).is_ok() {
                                *cur_com2 = Some(new_hk);
                            }
                        }
                    }
                }
            };

            sync_bindings(&hotkey_mgr, &mut active_com1, &mut active_com2);

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
                sync_bindings(&hotkey_mgr, &mut active_com1, &mut active_com2);
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
