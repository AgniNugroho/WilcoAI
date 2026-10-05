/// X-Plane 12 UDP packet builder and parser
///
/// Implements RREF (Request Data Ref) and DREF (Set Data Ref) binary protocols
/// as specified by the Laminar Research X-Plane UDP network specification.

/// Builds an RREF subscription packet requesting telemetry updates for a dataref.
///
/// Packet binary layout (413 bytes total):
/// - 5 bytes: "RREF\0" (ASCII null-terminated)
/// - 4 bytes: frequency in Hz (i32, little-endian)
/// - 4 bytes: integer identifier index chosen by client (i32, little-endian)
/// - 400 bytes: dataref name string, null-padded
pub fn build_rref_packet(freq_hz: i32, index: i32, dataref: &str) -> Vec<u8> {
    let mut packet = Vec::with_capacity(413);
    packet.extend_from_slice(b"RREF\0");
    packet.extend_from_slice(&freq_hz.to_le_bytes());
    packet.extend_from_slice(&index.to_le_bytes());

    let mut name_bytes = [0u8; 400];
    let dref_bytes = dataref.as_bytes();
    let copy_len = dref_bytes.len().min(400);
    name_bytes[..copy_len].copy_from_slice(&dref_bytes[..copy_len]);
    packet.extend_from_slice(&name_bytes);

    packet
}

/// Builds a DREF packet writing a single float32 value to an X-Plane dataref.
///
/// Packet binary layout (509 bytes total):
/// - 5 bytes: "DREF\0" (ASCII null-terminated)
/// - 4 bytes: float32 value (little-endian)
/// - 500 bytes: dataref name string, null-padded
pub fn build_dref_packet(value: f32, dataref: &str) -> Vec<u8> {
    let mut packet = Vec::with_capacity(509);
    packet.extend_from_slice(b"DREF\0");
    packet.extend_from_slice(&value.to_le_bytes());

    let mut name_bytes = [0u8; 500];
    let dref_bytes = dataref.as_bytes();
    let copy_len = dref_bytes.len().min(500);
    name_bytes[..copy_len].copy_from_slice(&dref_bytes[..copy_len]);
    packet.extend_from_slice(&name_bytes);

    packet
}

/// Parses an incoming X-Plane RREF response payload.
///
/// Headers supported:
/// - 5 bytes: "RREF\0" or "RREF," (standard X-Plane UDP)
/// - 6 bytes: "RREF,\0" (variant simulation/legacy)
/// - 4 bytes: "RREF"
///
/// Each subsequent record is 8 bytes:
/// - 4 bytes: index (i32, little-endian)
/// - 4 bytes: value (f32, little-endian)
///
/// Returns a Vec of (index, value) tuples without panicking on trailing bytes or jitter.
pub fn parse_rref_payload(buf: &[u8]) -> Vec<(i32, f32)> {
    if buf.len() < 5 || !buf.starts_with(b"RREF") {
        return Vec::new();
    }

    // Determine header offset based on explicit prefix and 8-byte chunk alignment
    let offset = if buf.len() >= 6 && &buf[..6] == b"RREF,\0" {
        6
    } else if (buf.len() - 5) % 8 == 0 {
        5
    } else if buf.len() >= 6 && (buf.len() - 6) % 8 == 0 {
        6
    } else if (buf.len() - 4) % 8 == 0 {
        4
    } else {
        5
    };

    if buf.len() < offset {
        return Vec::new();
    }

    let remaining = &buf[offset..];
    let num_records = remaining.len() / 8;
    let mut records = Vec::with_capacity(num_records);

    for chunk in remaining.chunks_exact(8) {
        let index = i32::from_le_bytes(chunk[0..4].try_into().unwrap());
        let value = f32::from_le_bytes(chunk[4..8].try_into().unwrap());
        records.push((index, value));
    }

    records
}
