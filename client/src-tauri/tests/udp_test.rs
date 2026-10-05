use wilco_client::xplane::listener::AircraftSnapshot;
use wilco_client::xplane::packet::{build_dref_packet, build_rref_packet, parse_rref_payload};
use wilco_client::xplane::sender::{build_atc_mute_packet, DREF_ATC_VOLUME_RATIO};
use wilco_client::xplane::*;

#[test]
fn test_build_rref_packet_structure_and_length() {
    let freq_hz = 10;
    let index = 1;
    let dataref = "sim/cockpit2/radios/actuators/com1_frequency_hz_833";

    let packet = build_rref_packet(freq_hz, index, dataref);

    // Total length must be 413 bytes:
    // 5 bytes header ("RREF\0") + 4 bytes freq + 4 bytes index + 400 bytes dataref string
    assert_eq!(packet.len(), 413);

    // Verify 5-byte header
    assert_eq!(&packet[0..5], b"RREF\0");

    // Verify freq_hz (i32 little-endian)
    let parsed_freq = i32::from_le_bytes(packet[5..9].try_into().unwrap());
    assert_eq!(parsed_freq, 10);

    // Verify index (i32 little-endian)
    let parsed_index = i32::from_le_bytes(packet[9..13].try_into().unwrap());
    assert_eq!(parsed_index, 1);

    // Verify null-padded dataref string in remaining 400 bytes
    let dref_bytes = dataref.as_bytes();
    assert_eq!(&packet[13..13 + dref_bytes.len()], dref_bytes);

    // Remaining bytes up to 413 must be null (0x00)
    for (i, &b) in packet[13 + dref_bytes.len()..413].iter().enumerate() {
        assert_eq!(b, 0, "byte at {} is not null", 13 + dref_bytes.len() + i);
    }
}

#[test]
fn test_parse_rref_payload_single_record() {
    // 5-byte header "RREF\0" + 4-byte index + 4-byte float32
    let mut payload = Vec::new();
    payload.extend_from_slice(b"RREF\0");
    payload.extend_from_slice(&1i32.to_le_bytes()); // index = 1
    payload.extend_from_slice(&118200000.0f32.to_le_bytes()); // COM1 freq = 118.200 MHz

    let records = parse_rref_payload(&payload);
    assert_eq!(records.len(), 1);
    assert_eq!(records[0].0, 1);
    assert!((records[0].1 - 118200000.0).abs() < 1e-3);
}

#[test]
fn test_parse_rref_payload_multiple_records_both_headers() {
    // Test 1: 5-byte header "RREF\0" with 3 records
    let mut payload_5b = Vec::new();
    payload_5b.extend_from_slice(b"RREF\0");
    // Record 1: index 1, value 118200000.0
    payload_5b.extend_from_slice(&1i32.to_le_bytes());
    payload_5b.extend_from_slice(&118200000.0f32.to_le_bytes());
    // Record 2: index 4, value -7.9077 (latitude)
    payload_5b.extend_from_slice(&4i32.to_le_bytes());
    payload_5b.extend_from_slice(&(-7.9077f32).to_le_bytes());
    // Record 3: index 8, value 1.0 (on_ground)
    payload_5b.extend_from_slice(&8i32.to_le_bytes());
    payload_5b.extend_from_slice(&1.0f32.to_le_bytes());

    let records_5b = parse_rref_payload(&payload_5b);
    assert_eq!(records_5b.len(), 3);
    assert_eq!(records_5b[0].0, 1);
    assert!((records_5b[0].1 - 118200000.0).abs() < 1e-3);
    assert_eq!(records_5b[1].0, 4);
    assert!((records_5b[1].1 - (-7.9077)).abs() < 1e-4);
    assert_eq!(records_5b[2].0, 8);
    assert!((records_5b[2].1 - 1.0).abs() < 1e-4);

    // Test 2: 6-byte header "RREF,\0" with 2 records
    let mut payload_6b = Vec::new();
    payload_6b.extend_from_slice(b"RREF,\0");
    // Record 1: index 2, value 121650000.0
    payload_6b.extend_from_slice(&2i32.to_le_bytes());
    payload_6b.extend_from_slice(&121650000.0f32.to_le_bytes());
    // Record 2: index 9, value 5201.0 (transponder)
    payload_6b.extend_from_slice(&9i32.to_le_bytes());
    payload_6b.extend_from_slice(&5201.0f32.to_le_bytes());

    let records_6b = parse_rref_payload(&payload_6b);
    assert_eq!(records_6b.len(), 2);
    assert_eq!(records_6b[0].0, 2);
    assert!((records_6b[0].1 - 121650000.0).abs() < 1e-3);
    assert_eq!(records_6b[1].0, 9);
    assert!((records_6b[1].1 - 5201.0).abs() < 1e-3);
}

#[test]
fn test_build_dref_packet_volume_mute() {
    let packet = build_dref_packet(0.0, DREF_ATC_VOLUME_RATIO);

    // Total length must be 509 bytes:
    // 5 bytes header ("DREF\0") + 4 bytes float value + 500 bytes dataref string
    assert_eq!(packet.len(), 509);

    // Verify 5-byte header
    assert_eq!(&packet[0..5], b"DREF\0");

    // Verify float value (0.0f32 little-endian)
    let parsed_val = f32::from_le_bytes(packet[5..9].try_into().unwrap());
    assert_eq!(parsed_val, 0.0);

    // Verify null-padded dataref string in remaining 500 bytes
    let dref_bytes = DREF_ATC_VOLUME_RATIO.as_bytes();
    assert_eq!(&packet[9..9 + dref_bytes.len()], dref_bytes);

    // Remaining bytes up to 509 must be null (0x00)
    for (i, &b) in packet[9 + dref_bytes.len()..509].iter().enumerate() {
        assert_eq!(b, 0, "byte at {} is not null", 9 + dref_bytes.len() + i);
    }

    // Helper build_atc_mute_packet() must produce identical payload
    let mute_packet = build_atc_mute_packet();
    assert_eq!(mute_packet, packet);
}

#[test]
fn test_aircraft_snapshot_update_from_records() {
    let mut snapshot = AircraftSnapshot::default();

    let records = vec![
        (IDX_COM1_FREQ, 118200000.0),
        (IDX_COM2_FREQ, 121650000.0),
        (IDX_AUDIO_COM_SELECTION, 2.0),
        (IDX_LATITUDE, -7.9077),
        (IDX_LONGITUDE, 110.0544),
        (IDX_ELEVATION, 35.5),
        (IDX_Y_AGL, 2.1),
        (IDX_ON_GROUND, 1.0),
        (IDX_TRANSPONDER_CODE, 5201.0),
        (IDX_BAROMETER_PILOT, 29.92),
        (IDX_GROUNDSPEED, 0.0),
        (IDX_WIND_SPEED, 7.0),
        (IDX_WIND_DIR, 100.0),
    ];

    snapshot.apply_records(&records);

    assert_eq!(snapshot.com1_hz, 118200000);
    assert_eq!(snapshot.com2_hz, 121650000);
    assert_eq!(snapshot.active_radio, 2);
    assert!((snapshot.lat - -7.9077).abs() < 1e-4);
    assert!((snapshot.lon - 110.0544).abs() < 1e-4);
    assert!((snapshot.elevation_m - 35.5).abs() < 1e-4);
    assert!((snapshot.agl_m - 2.1).abs() < 1e-4);
    assert!(snapshot.on_ground);
    assert_eq!(snapshot.squawk, 5201);
    assert!((snapshot.qnh_inhg - 29.92).abs() < 1e-4);
    assert_eq!(snapshot.groundspeed_ms, 0.0);
    assert!((snapshot.wind_speed - 7.0).abs() < 1e-4);
    assert!((snapshot.wind_dir - 100.0).abs() < 1e-4);
}

#[test]
fn test_aircraft_snapshot_serde_json() {
    let mut snapshot = AircraftSnapshot::default();
    snapshot.com1_hz = 118200000;
    snapshot.active_radio = 1;
    snapshot.squawk = 5201;

    let json_str = serde_json::to_string(&snapshot).expect("serialize snapshot");
    assert!(json_str.contains("\"com1_hz\":118200000"));
    assert!(json_str.contains("\"squawk\":5201"));

    let deserialized: AircraftSnapshot = serde_json::from_str(&json_str).expect("deserialize snapshot");
    assert_eq!(deserialized.com1_hz, 118200000);
    assert_eq!(deserialized.squawk, 5201);
}

#[tokio::test]
async fn test_xplane_udp_manager_mock_lifecycle() {
    use std::sync::Arc;
    use tokio::net::UdpSocket;
    use std::time::Duration;

    // 1. Setup mock X-Plane UDP listener
    let mock_xplane = UdpSocket::bind("127.0.0.1:0").await.expect("bind mock xplane");
    let mock_addr = mock_xplane.local_addr().expect("mock addr");

    // 2. Setup manager targeting mock X-Plane socket
    let manager = Arc::new(
        XPlaneUdpManager::new("127.0.0.1:0", &mock_addr.to_string())
            .expect("create manager")
    );

    let handle = manager.clone().spawn_background();

    // 3. Mock socket receives mute packet
    let mut buf = [0u8; 1024];
    let (len, client_addr) = mock_xplane.recv_from(&mut buf).await.expect("recv mute packet");
    assert_eq!(&buf[0..5], b"DREF\0");
    let vol = f32::from_le_bytes(buf[5..9].try_into().unwrap());
    assert_eq!(vol, 0.0);

    // 4. Mock socket sends RREF response to client
    let mut sim_payload = Vec::new();
    sim_payload.extend_from_slice(b"RREF\0");
    // COM1 frequency update: 118.200 MHz
    sim_payload.extend_from_slice(&IDX_COM1_FREQ.to_le_bytes());
    sim_payload.extend_from_slice(&118200000.0f32.to_le_bytes());
    // Squawk update: 5201
    sim_payload.extend_from_slice(&IDX_TRANSPONDER_CODE.to_le_bytes());
    sim_payload.extend_from_slice(&5201.0f32.to_le_bytes());

    mock_xplane.send_to(&sim_payload, client_addr).await.expect("send rref response");

    // 5. Wait for snapshot to reflect updates
    let mut updated = false;
    for _ in 0..20 {
        tokio::time::sleep(Duration::from_millis(25)).await;
        let snap = manager.get_snapshot().await;
        if snap.com1_hz == 118200000 && snap.squawk == 5201 {
            updated = true;
            break;
        }
    }
    assert!(updated, "snapshot should update with telemetry from mock X-Plane");
    assert!(manager.is_connected());

    // 6. Stop manager and verify unmute packet
    manager.stop();
    let _ = handle.await;

    // Receive until unmute packet or timeout
    let mut received_unmute = false;
    let timeout = tokio::time::sleep(Duration::from_millis(500));
    tokio::pin!(timeout);

    loop {
        tokio::select! {
            res = mock_xplane.recv_from(&mut buf) => {
                if let Ok((len, _)) = res {
                    if len >= 9 && &buf[0..5] == b"DREF\0" {
                        let vol = f32::from_le_bytes(buf[5..9].try_into().unwrap());
                        if (vol - 1.0).abs() < 1e-4 {
                            received_unmute = true;
                            break;
                        }
                    }
                }
            }
            _ = &mut timeout => {
                break;
            }
        }
    }
    assert!(received_unmute, "manager should restore ATC volume (1.0) on shutdown");
}

