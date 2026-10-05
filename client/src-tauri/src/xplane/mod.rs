pub mod listener;
pub mod packet;
pub mod sender;

pub use listener::{AircraftSnapshot, XPlaneUdpManager};
pub use packet::{build_dref_packet, build_rref_packet, parse_rref_payload};
pub use sender::{build_atc_mute_packet, build_atc_unmute_packet, DREF_ATC_VOLUME_RATIO};

// Monitored dataref paths
pub const DREF_COM1_FREQ: &str = "sim/cockpit2/radios/actuators/com1_frequency_hz_833";
pub const DREF_COM2_FREQ: &str = "sim/cockpit2/radios/actuators/com2_frequency_hz_833";
pub const DREF_AUDIO_COM_SELECTION: &str = "sim/cockpit2/radios/actuators/audio_com_selection";
pub const DREF_LATITUDE: &str = "sim/flightmodel/position/latitude";
pub const DREF_LONGITUDE: &str = "sim/flightmodel/position/longitude";
pub const DREF_ELEVATION: &str = "sim/flightmodel/position/elevation";
pub const DREF_Y_AGL: &str = "sim/flightmodel/position/y_agl";
pub const DREF_ON_GROUND: &str = "sim/flightmodel2/gear/on_ground[0]";
pub const DREF_TRANSPONDER_CODE: &str = "sim/cockpit/radios/transponder_code";
pub const DREF_BAROMETER_PILOT: &str = "sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot";
pub const DREF_GROUNDSPEED: &str = "sim/flightmodel/position/groundspeed";
pub const DREF_WIND_SPEED_KTS: &str = "sim/weather/aircraft/wind_speed_kts";
pub const DREF_WIND_DIR_DEGS: &str = "sim/weather/aircraft/wind_direction_degs";

// Monitored dataref index identifiers
pub const IDX_COM1_FREQ: i32 = 1;
pub const IDX_COM2_FREQ: i32 = 2;
pub const IDX_AUDIO_COM_SELECTION: i32 = 3;
pub const IDX_LATITUDE: i32 = 4;
pub const IDX_LONGITUDE: i32 = 5;
pub const IDX_ELEVATION: i32 = 6;
pub const IDX_Y_AGL: i32 = 7;
pub const IDX_ON_GROUND: i32 = 8;
pub const IDX_TRANSPONDER_CODE: i32 = 9;
pub const IDX_BAROMETER_PILOT: i32 = 10;
pub const IDX_GROUNDSPEED: i32 = 11;
pub const IDX_WIND_SPEED: i32 = 12;
pub const IDX_WIND_DIR: i32 = 13;

pub const MONITORED_DATAREFS: &[(i32, &str)] = &[
    (IDX_COM1_FREQ, DREF_COM1_FREQ),
    (IDX_COM2_FREQ, DREF_COM2_FREQ),
    (IDX_AUDIO_COM_SELECTION, DREF_AUDIO_COM_SELECTION),
    (IDX_LATITUDE, DREF_LATITUDE),
    (IDX_LONGITUDE, DREF_LONGITUDE),
    (IDX_ELEVATION, DREF_ELEVATION),
    (IDX_Y_AGL, DREF_Y_AGL),
    (IDX_ON_GROUND, DREF_ON_GROUND),
    (IDX_TRANSPONDER_CODE, DREF_TRANSPONDER_CODE),
    (IDX_BAROMETER_PILOT, DREF_BAROMETER_PILOT),
    (IDX_GROUNDSPEED, DREF_GROUNDSPEED),
    (IDX_WIND_SPEED, DREF_WIND_SPEED_KTS),
    (IDX_WIND_DIR, DREF_WIND_DIR_DEGS),
];
