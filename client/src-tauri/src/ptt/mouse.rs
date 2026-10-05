use std::sync::atomic::{AtomicBool, Ordering};
#[cfg(windows)]
use std::sync::atomic::AtomicU32;
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
const WM_QUIT: u32 = 0x0012;
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
    fn GetCurrentThreadId() -> u32;
    fn SetWindowsHookExW(
        id_hook: i32,
        lpfn: Option<unsafe extern "system" fn(i32, usize, isize) -> isize>,
        hmod: isize,
        dw_thread_id: u32,
    ) -> isize;
    fn UnhookWindowsHookEx(hhk: isize) -> i32;
    fn CallNextHookEx(hhk: isize, n_code: i32, wparam: usize, lparam: isize) -> isize;
    fn GetMessageW(msg: *mut WinMsg, hwnd: isize, filter_min: u32, filter_max: u32) -> i32;
    fn PostThreadMessageW(id_thread: u32, msg: u32, wparam: usize, lparam: isize) -> i32;
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
            let mut handled = false;
            if let Ok(guard) = MOUSE_MANAGER.lock() {
                if let Some(ref mgr) = *guard {
                    handled = if is_down {
                        mgr.handle_mouse_press(btn)
                    } else {
                        mgr.handle_mouse_release(btn)
                    };
                }
            }
            // If this event was consumed by PTT (active binding or learning mode), swallow it
            // to avoid unwanted side effects (e.g. browser back/forward navigation)
            if handled {
                return 1;
            }
        }
    }

    CallNextHookEx(0, n_code, wparam, lparam)
}

/// Background global listener that monitors mouse thumb buttons (Mouse 4/5) and middle click (Mouse 3)
pub struct MouseListener {
    running: Arc<AtomicBool>,
    #[cfg(windows)]
    win_thread_id: Arc<AtomicU32>,
    manager: PttManager,
    thread_handle: Option<JoinHandle<()>>,
}

impl MouseListener {
    /// Create a new mouse listener associated with a `PttManager`
    pub fn new(manager: PttManager) -> Self {
        Self {
            running: Arc::new(AtomicBool::new(false)),
            #[cfg(windows)]
            win_thread_id: Arc::new(AtomicU32::new(0)),
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
        #[cfg(windows)]
        let win_thread_id = Arc::clone(&self.win_thread_id);
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
                let tid = unsafe { GetCurrentThreadId() };
                win_thread_id.store(tid, Ordering::SeqCst);
                if !running.load(Ordering::Relaxed) {
                    win_thread_id.store(0, Ordering::SeqCst);
                    running.store(false, Ordering::SeqCst);
                    return;
                }

                let hook = unsafe { SetWindowsHookExW(WH_MOUSE_LL, Some(mouse_hook_proc), 0, 0) };
                if hook == 0 {
                    eprintln!("Warning: Failed to install Windows WH_MOUSE_LL low-level mouse hook");
                    win_thread_id.store(0, Ordering::SeqCst);
                    running.store(false, Ordering::SeqCst);
                    return;
                }

                // Standard blocking Windows message pump: zero CPU usage while idle,
                // zero cursor stutter/delay, woken up immediately on WM_QUIT or mouse events.
                let mut msg = unsafe { std::mem::zeroed::<WinMsg>() };
                while running.load(Ordering::Relaxed) {
                    let ret = unsafe { GetMessageW(&mut msg, 0, 0, 0) };
                    if ret <= 0 {
                        // 0 indicates WM_QUIT; -1 indicates error
                        break;
                    }
                    unsafe {
                        TranslateMessage(&msg);
                        DispatchMessageW(&msg);
                    }
                }

                unsafe {
                    UnhookWindowsHookEx(hook);
                }
                win_thread_id.store(0, Ordering::SeqCst);
            }

            #[cfg(not(windows))]
            {
                let _ = manager;
                while running.load(Ordering::Relaxed) {
                    thread::sleep(Duration::from_millis(50));
                }
            }

            running.store(false, Ordering::SeqCst);
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
                // Signal hook thread to break out of GetMessageW immediately
                let mut tid = self.win_thread_id.swap(0, Ordering::SeqCst);
                if tid == 0 {
                    for _ in 0..50 {
                        tid = self.win_thread_id.swap(0, Ordering::SeqCst);
                        if tid != 0 {
                            break;
                        }
                        thread::sleep(Duration::from_millis(1));
                    }
                }
                if tid != 0 {
                    unsafe {
                        PostThreadMessageW(tid, WM_QUIT, 0, 0);
                    }
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

