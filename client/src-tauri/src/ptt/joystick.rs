use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::Duration;

use gilrs::{EventType, Gilrs};

use crate::ptt::PttManager;

/// Background listener that polls joystick / flight yoke controllers via `gilrs`
pub struct JoystickListener {
    running: Arc<AtomicBool>,
    manager: PttManager,
    thread_handle: Option<JoinHandle<()>>,
}

impl JoystickListener {
    /// Create a new joystick listener associated with a `PttManager`
    pub fn new(manager: PttManager) -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            manager,
            thread_handle: None,
        }
    }

    /// Returns whether the background polling thread is active
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::Relaxed)
    }

    /// Starts polling gamepads and joysticks in a background thread
    pub fn start(&mut self) {
        if self.is_running() {
            return;
        }

        self.running.store(true, Ordering::SeqCst);
        let running = Arc::clone(&self.running);
        let manager = self.manager.clone();

        let handle = thread::spawn(move || {
            let mut gilrs = match Gilrs::new() {
                Ok(g) => g,
                Err(err) => {
                    eprintln!("Warning: Failed to initialize Gilrs joystick subsystem: {:?}", err);
                    running.store(false, Ordering::SeqCst);
                    return;
                }
            };

            while running.load(Ordering::Relaxed) {
                let mut processed_any = false;
                while let Some(ev) = gilrs.next_event() {
                    processed_any = true;
                    match ev.event {
                        EventType::ButtonPressed(_button, code) => {
                            let button_code = code.into_u32();
                            manager.handle_joystick_press(button_code);
                        }
                        EventType::ButtonReleased(_button, code) => {
                            let button_code = code.into_u32();
                            manager.handle_joystick_release(button_code);
                        }
                        _ => {}
                    }
                }

                // If no event was received, sleep briefly to avoid pegging CPU core
                if !processed_any {
                    thread::sleep(Duration::from_millis(10));
                }
            }

            running.store(false, Ordering::SeqCst);
        });

        self.thread_handle = Some(handle);
    }

    /// Stops the polling thread and waits for it to join
    pub fn stop(&mut self) {
        if self.running.swap(false, Ordering::SeqCst) {
            if let Some(handle) = self.thread_handle.take() {
                let _ = handle.join();
            }
        }
    }
}

impl Drop for JoystickListener {
    fn drop(&mut self) {
        self.stop();
    }
}
