use std::net::SocketAddr;
use tokio::net::UdpSocket;

use super::packet::{build_dref_packet, build_rref_packet};
use super::MONITORED_DATAREFS;

/// Dataref controlling default X-Plane ATC speech synthesizer volume
pub const DREF_ATC_VOLUME_RATIO: &str = "sim/operation/sound/radio_atc_volume_ratio";

/// Builds a DREF packet to mute the built-in X-Plane ATC audio (volume = 0.0)
pub fn build_atc_mute_packet() -> Vec<u8> {
    build_dref_packet(0.0, DREF_ATC_VOLUME_RATIO)
}

/// Builds a DREF packet to restore the built-in X-Plane ATC audio (volume = 1.0)
pub fn build_atc_unmute_packet() -> Vec<u8> {
    build_dref_packet(1.0, DREF_ATC_VOLUME_RATIO)
}

/// Builds all RREF subscription packets for the monitored aircraft telemetry datarefs
pub fn build_all_rref_subscriptions(freq_hz: i32) -> Vec<Vec<u8>> {
    MONITORED_DATAREFS
        .iter()
        .map(|&(idx, name)| build_rref_packet(freq_hz, idx, name))
        .collect()
}

/// Sends the ATC volume mute packet over a UDP socket to the target address
pub async fn send_atc_mute(socket: &UdpSocket, target: SocketAddr) -> std::io::Result<usize> {
    let packet = build_atc_mute_packet();
    socket.send_to(&packet, target).await
}

/// Sends the ATC volume unmute packet over a UDP socket to the target address
pub async fn send_atc_unmute(socket: &UdpSocket, target: SocketAddr) -> std::io::Result<usize> {
    let packet = build_atc_unmute_packet();
    socket.send_to(&packet, target).await
}

/// Dispatches subscription packets for all monitored datarefs at the specified frequency
pub async fn send_all_subscriptions(
    socket: &UdpSocket,
    target: SocketAddr,
    freq_hz: i32,
) -> std::io::Result<()> {
    for packet in build_all_rref_subscriptions(freq_hz) {
        socket.send_to(&packet, target).await?;
    }
    Ok(())
}
