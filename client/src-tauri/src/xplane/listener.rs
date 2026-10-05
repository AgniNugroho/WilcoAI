use std::net::SocketAddr;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use serde::{Deserialize, Serialize};
use tokio::net::UdpSocket;
use tokio::sync::{broadcast, RwLock};

use super::packet::parse_rref_payload;
use super::sender::{send_all_subscriptions, send_atc_mute, send_atc_unmute};
use super::*;

/// Aircraft telemetry snapshot ingested from X-Plane 12 UDP datarefs
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AircraftSnapshot {
    pub com1_hz: i32,
    pub com2_hz: i32,
    pub active_radio: i32,
    pub lat: f64,
    pub lon: f64,
    pub elevation_m: f32,
    pub agl_m: f32,
    pub on_ground: bool,
    pub squawk: i32,
    pub qnh_inhg: f32,
    pub groundspeed_ms: f32,
    pub wind_speed: f32,
    pub wind_dir: f32,
}

impl Default for AircraftSnapshot {
    fn default() -> Self {
        Self {
            com1_hz: 118_200_000,
            com2_hz: 121_650_000,
            active_radio: 1,
            lat: 0.0,
            lon: 0.0,
            elevation_m: 0.0,
            agl_m: 0.0,
            on_ground: true,
            squawk: 1200,
            qnh_inhg: 29.92,
            groundspeed_ms: 0.0,
            wind_speed: 0.0,
            wind_dir: 0.0,
        }
    }
}

impl AircraftSnapshot {
    /// Updates a single field according to its dataref index identifier
    pub fn update_field(&mut self, index: i32, value: f32) {
        match index {
            IDX_COM1_FREQ => {
                self.com1_hz = parse_frequency_val(value);
            }
            IDX_COM2_FREQ => {
                self.com2_hz = parse_frequency_val(value);
            }
            IDX_AUDIO_COM_SELECTION => {
                let radio = value.round() as i32;
                self.active_radio = if radio == 2 { 2 } else { 1 };
            }
            IDX_LATITUDE => {
                self.lat = value as f64;
            }
            IDX_LONGITUDE => {
                self.lon = value as f64;
            }
            IDX_ELEVATION => {
                self.elevation_m = value;
            }
            IDX_Y_AGL => {
                self.agl_m = value;
            }
            IDX_ON_GROUND => {
                self.on_ground = value > 0.5;
            }
            IDX_TRANSPONDER_CODE => {
                self.squawk = value.round() as i32;
            }
            IDX_BAROMETER_PILOT => {
                self.qnh_inhg = value;
            }
            IDX_GROUNDSPEED => {
                self.groundspeed_ms = value;
            }
            IDX_WIND_SPEED => {
                self.wind_speed = value;
            }
            IDX_WIND_DIR => {
                self.wind_dir = value;
            }
            _ => {}
        }
    }

    /// Batch applies parsed dataref records to the snapshot
    pub fn apply_records(&mut self, records: &[(i32, f32)]) {
        for &(index, value) in records {
            self.update_field(index, value);
        }
    }

    /// Returns the currently active radio frequency in Hz
    pub fn active_frequency_hz(&self) -> i32 {
        if self.active_radio == 2 {
            self.com2_hz
        } else {
            self.com1_hz
        }
    }

    /// Returns the human-readable identifier for the active transmitting radio
    pub fn active_radio_name(&self) -> &'static str {
        if self.active_radio == 2 {
            "COM2"
        } else {
            "COM1"
        }
    }
}

/// Normalizes floating point frequency values from various X-Plane datarefs to integer Hz
fn parse_frequency_val(val: f32) -> i32 {
    if val > 1_000_000.0 {
        // e.g. 118200000.0 (Hz)
        val.round() as i32
    } else if val > 100_000.0 {
        // e.g. 118200.0 (kHz)
        (val * 1_000.0).round() as i32
    } else if val > 10_000.0 {
        // e.g. 11820.0 (10 kHz spacing)
        (val * 10_000.0).round() as i32
    } else if val > 100.0 {
        // e.g. 118.2 (MHz)
        (val * 1_000_000.0).round() as i32
    } else {
        val.round() as i32
    }
}

/// Background UDP Manager handling bidirectional communication with X-Plane 12
#[derive(Clone)]
pub struct XPlaneUdpManager {
    snapshot: Arc<RwLock<AircraftSnapshot>>,
    bind_addr: String,
    target_addr: SocketAddr,
    is_connected: Arc<AtomicBool>,
    shutdown_tx: broadcast::Sender<()>,
}

impl XPlaneUdpManager {
    /// Creates a new manager targeting the specified simulator socket
    pub fn new(bind_addr: &str, target_addr: &str) -> Result<Self, std::io::Error> {
        let parsed_target: SocketAddr = target_addr.parse().map_err(|e| {
            std::io::Error::new(std::io::ErrorKind::InvalidInput, format!("Invalid target: {e}"))
        })?;
        let (shutdown_tx, _) = broadcast::channel(1);

        Ok(Self {
            snapshot: Arc::new(RwLock::new(AircraftSnapshot::default())),
            bind_addr: bind_addr.to_string(),
            target_addr: parsed_target,
            is_connected: Arc::new(AtomicBool::new(false)),
            shutdown_tx,
        })
    }

    /// Creates a manager configured for standard local X-Plane 12 port 49000
    pub fn default_local() -> Result<Self, std::io::Error> {
        Self::new("0.0.0.0:0", "127.0.0.1:49000")
    }

    /// Returns the thread-safe reference handle to the aircraft snapshot
    pub fn snapshot_handle(&self) -> Arc<RwLock<AircraftSnapshot>> {
        Arc::clone(&self.snapshot)
    }

    /// Returns a copy of the current snapshot
    pub async fn get_snapshot(&self) -> AircraftSnapshot {
        self.snapshot.read().await.clone()
    }

    /// Indicates whether active UDP telemetry is being received
    pub fn is_connected(&self) -> bool {
        self.is_connected.load(Ordering::Relaxed)
    }

    /// Signals the background UDP task to shut down gracefully and restore ATC audio
    pub fn stop(&self) {
        let _ = self.shutdown_tx.send(());
    }

    /// Spawns the background receiver and keepalive tasks
    pub fn spawn_background(self: Arc<Self>) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            if let Err(e) = self.run_loop().await {
                eprintln!("[XPlaneUdpManager] run_loop error: {e}");
            }
        })
    }

    /// Runs the core UDP socket loop: keepalive subscriptions and packet ingestion
    pub async fn run_loop(&self) -> Result<(), std::io::Error> {
        let socket = Arc::new(UdpSocket::bind(&self.bind_addr).await?);
        let target = self.target_addr;

        // 1. Mute default X-Plane ATC speech volume
        let _ = send_atc_mute(&socket, target).await;

        // 2. Initial RREF subscriptions
        let _ = send_all_subscriptions(&socket, target, 10).await;

        let socket_send = Arc::clone(&socket);
        let mut shutdown_rx_keepalive = self.shutdown_tx.subscribe();

        // Background keepalive task: resend subscriptions every 5 seconds
        let keepalive_task = tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(5));
            loop {
                tokio::select! {
                    _ = interval.tick() => {
                        let _ = send_all_subscriptions(&socket_send, target, 10).await;
                    }
                    _ = shutdown_rx_keepalive.recv() => {
                        break;
                    }
                }
            }
        });

        let mut shutdown_rx_loop = self.shutdown_tx.subscribe();
        let mut buf = [0u8; 4096];

        loop {
            tokio::select! {
                res = socket.recv_from(&mut buf) => {
                    match res {
                        Ok((len, _from)) => {
                            let records = parse_rref_payload(&buf[..len]);
                            if !records.is_empty() {
                                self.is_connected.store(true, Ordering::Relaxed);
                                let mut snap = self.snapshot.write().await;
                                snap.apply_records(&records);
                            }
                        }
                        Err(e) => {
                            eprintln!("[XPlaneUdpManager] recv error: {e}");
                        }
                    }
                }
                _ = shutdown_rx_loop.recv() => {
                    break;
                }
            }
        }

        // Cancel keepalive and unmute ATC before exiting
        keepalive_task.abort();
        let _ = send_atc_unmute(&socket, target).await;
        self.is_connected.store(false, Ordering::Relaxed);

        Ok(())
    }
}
