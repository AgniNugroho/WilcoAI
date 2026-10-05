use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::Duration;

#[cfg(windows)]
use std::sync::Mutex;

use crate::ptt::PttManager;

#[cfg(windows)]
static MOUSE_MANAGER: Mutex<Option<PttManager>> = Mutex::new(None);

#[cfg(windows)]
const WH_MOUSE_LL: i32 = 14;
#[cfg(windows)]
const WM_MBUTTONDOWN: u32 = 0x0207;
#[cfg(windows)]
const WM_MBUTTONUP: u32 = 0x0208;
#[cfg(windows)]
const WM_XBUTTONDOWN: u32 = 0x020B;
#[cfg(windows)]
const WM_XBUTTONUP: u32 = 0x020C;

#[cfg(windows)]
#[repr(C)]
struct Point {
    x: i32,
    y: i32,
}

#[cfg(windows)]
#[repr(C)]
struct MsllHookStruct {
    pt: Point,
    mouse_data: u32,
    flags: u32,
    time: u32,
    dw_extra_info: usize,
}

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
    fn SetWindowsHookExW(
        id_hook: i32,
        lpfn: Option<unsafe extern "system" fn(i32, usize, isize) -> isize>,
        hmod: isize,
        dw_thread_id: u32,
    ) -> isize;
    fn UnhookWindowsHookEx(hhk: isize) -> i32;
    fn CallNextHookEx(hhk: isize, n_code: i32, wparam: usize, lparam: isize) -> isize;
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

#[cfg(windows)]
unsafe extern "system" fn mouse_hook_proc(n_code: i32, wparam: usize, lparam: isize) -> isize {
    if n_code >= 0 && lparam != 0 {
        let info = &*(lparam as *const MsllHookStruct);
        let msg = wparam as u32;

        let button = match msg {
            WM_XBUTTONDOWN | WM_XBUTTONUP => {
                let hiword = ((info.mouse_data >> 16) & 0xFFFF) as u16;
                if hiword == 1 {
                    Some(4) // Mouse 4 (Thumb Back / XBUTTON1)
                } else if hiword == 2 {
                    Some(5) // Mouse 5 (Thumb Forward / XBUTTON2)
                } else {
                    None
                }
            }
            WM_MBUTTONDOWN | WM_MBUTTONUP => Some(3), // Middle Mouse Button (Mouse 3)
            _ => None,
        };

        if let Some(btn) = button {
            let is_down = msg == WM_XBUTTONDOWN || msg == WM_MBUTTONDOWN;
            if let Ok(guard) = MOUSE_MANAGER.lock() {
                if let Some(ref mgr) = *guard {
                    if is_down {
                        mgr.handle_mouse_press(btn);
                    } else {
                        mgr.handle_mouse_release(btn);
                    }
                }
            }
        }
    }

    CallNextHookEx(0, n_code, wparam, lparam)
}

/// Background global listener that monitors mouse thumb buttons (Mouse 4/5) and middle click (Mouse 3)
pub struct MouseListener {
    running: Arc<AtomicBool>,
    manager: PttManager,
    thread_handle: Option<JoinHandle<()>>,
}

impl MouseListener {
    /// Create a new mouse listener associated with a `PttManager`
    pub fn new(manager: PttManager) -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            manager,
            thread_handle: None,
        }
    }

    /// Returns whether the mouse listener thread is active
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::Relaxed)
    }

    /// Starts monitoring mouse thumb button events in a background thread
    pub fn start(&mut self) {
        if self.is_running() {
            return;
        }

        self.running.store(true, Ordering::SeqCst);
        let running = Arc::clone(&self.running);
        let manager = self.manager.clone();

        #[cfg(windows)]
        {
            if let Ok(mut guard) = MOUSE_MANAGER.lock() {
                *guard = Some(manager);
            }
        }

        let handle = thread::spawn(move || {
            #[cfg(windows)]
            {
                let hook = unsafe { SetWindowsHookExW(WH_MOUSE_LL, Some(mouse_hook_proc), 0, 0) };
                if hook == 0 {
                    eprintln!("Warning: Failed to install Windows WH_MOUSE_LL low-level mouse hook");
                    running.store(false, Ordering::SeqCst);
                    return;
                }

                while running.load(Ordering::Relaxed) {
                    unsafe {
                        let mut msg = std::mem::zeroed::<WinMsg>();
                        while PeekMessageW(&mut msg, 0, 0, 0, 1) != 0 {
                            TranslateMessage(&msg);
                            DispatchMessageW(&msg);
                        }
                    }
                    thread::sleep(Duration::from_millis(10));
                }

                unsafe {
                    UnhookWindowsHookEx(hook);
                }
            }

            #[cfg(not(windows))]
            {
                let _ = manager;
                while running.load(Ordering::Relaxed) {
                    thread::sleep(Duration::from_millis(50));
                }
            }
        });

        self.thread_handle = Some(handle);
    }

    /// Stops the mouse listener thread and cleans up the Windows hook
    pub fn stop(&mut self) {
        if self.running.swap(false, Ordering::SeqCst) {
            #[cfg(windows)]
            {
                if let Ok(mut guard) = MOUSE_MANAGER.lock() {
                    *guard = None;
                }
            }

            if let Some(handle) = self.thread_handle.take() {
                let _ = handle.join();
            }
        }
    }
}

impl Drop for MouseListener {
    fn drop(&mut self) {
        self.stop();
    }
}
