use wilco_client::audio::dsp::{
    calculate_rms, generate_squelch_open, generate_squelch_tail, VhfDspFilter,
};
use wilco_client::audio::{AudioCapture, AudioPlayback};

/// Helper to calculate RMS of f32 samples
fn calculate_f32_rms(samples: &[f32]) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }
    let sum_sq: f64 = samples.iter().map(|&s| (s as f64) * (s as f64)).sum();
    (sum_sq / samples.len() as f64).sqrt() as f32
}

/// Helper to generate pure sine wave samples
fn generate_sine_wave(freq_hz: f32, sample_rate: u32, duration_secs: f32, amplitude: f32) -> Vec<f32> {
    let num_samples = (sample_rate as f32 * duration_secs) as usize;
    (0..num_samples)
        .map(|i| {
            let t = i as f32 / sample_rate as f32;
            amplitude * (2.0 * std::f32::consts::PI * freq_hz * t).sin()
        })
        .collect()
}

#[test]
fn test_bandpass_attenuation_low_and_high_frequencies() {
    let sample_rate = 24000;
    let duration = 0.3; // 300 ms -> 7200 samples

    // 1. Reference signal: 1000 Hz pure sine wave (within passband 300 - 3400 Hz)
    let ref_sine = generate_sine_wave(1000.0, sample_rate, duration, 1.0);
    let mut filter_ref = VhfDspFilter::new(sample_rate).with_noise(false);
    let mut ref_out = ref_sine.clone();
    filter_ref.process_buffer(&mut ref_out);

    // Measure steady-state RMS (discard first 2400 samples / 100 ms transient)
    let ref_rms = calculate_f32_rms(&ref_out[2400..]);
    assert!(ref_rms > 0.6, "Reference 1000 Hz passband RMS should be near unattenuated, got {}", ref_rms);

    // 2. Low stopband signal: 100 Hz (< 300 Hz cutoff)
    let low_sine = generate_sine_wave(100.0, sample_rate, duration, 1.0);
    let mut filter_low = VhfDspFilter::new(sample_rate).with_noise(false);
    let mut low_out = low_sine.clone();
    filter_low.process_buffer(&mut low_out);
    let low_rms = calculate_f32_rms(&low_out[2400..]);

    let low_attenuation_db = 20.0 * (ref_rms / low_rms.max(1e-9)).log10();
    println!("100 Hz attenuation: {:.2} dB (RMS: {:.6} vs ref {:.6})", low_attenuation_db, low_rms, ref_rms);
    assert!(
        low_attenuation_db >= 18.0,
        "Low frequency 100 Hz must be attenuated by at least 18 dB, got {:.2} dB",
        low_attenuation_db
    );

    // 3. High stopband signal: 6000 Hz (> 3400 Hz cutoff)
    let high_sine = generate_sine_wave(6000.0, sample_rate, duration, 1.0);
    let mut filter_high = VhfDspFilter::new(sample_rate).with_noise(false);
    let mut high_out = high_sine.clone();
    filter_high.process_buffer(&mut high_out);
    let high_rms = calculate_f32_rms(&high_out[2400..]);

    let high_attenuation_db = 20.0 * (ref_rms / high_rms.max(1e-9)).log10();
    println!("6000 Hz attenuation: {:.2} dB (RMS: {:.6} vs ref {:.6})", high_attenuation_db, high_rms, ref_rms);
    assert!(
        high_attenuation_db >= 18.0,
        "High frequency 6000 Hz must be attenuated by at least 18 dB, got {:.2} dB",
        high_attenuation_db
    );
}

#[test]
fn test_squelch_click_generation_length_and_finite_values() {
    let sample_rate = 24000;

    // Squelch open click: 25 ms @ 24 kHz = 600 samples
    let open_click = generate_squelch_open(sample_rate);
    assert_eq!(open_click.len(), 600, "Squelch open click must be 600 samples (25 ms @ 24 kHz)");
    
    // Also test through VhfDspFilter instance & static method
    let filter = VhfDspFilter::new(sample_rate);
    let open_click_inst = filter.squelch_open();
    assert_eq!(open_click_inst.len(), 600);
    assert_eq!(VhfDspFilter::generate_squelch_open(sample_rate).len(), 600);

    for (i, &s) in open_click.iter().enumerate() {
        assert!(s.is_finite(), "Squelch open sample {} is not finite: {}", i, s);
        assert!(!s.is_nan(), "Squelch open sample {} is NaN", i);
        assert!(s >= -1.0 && s <= 1.0, "Squelch open sample {} clipped out of [-1.0, 1.0]: {}", i, s);
    }
    // Verify it is not pure silence
    let open_energy: f32 = open_click.iter().map(|&s| s.abs()).sum();
    assert!(open_energy > 0.1, "Squelch open click must contain non-zero audio content");

    // Squelch tail click: 60 ms @ 24 kHz = 1440 samples
    let tail_click = generate_squelch_tail(sample_rate);
    assert_eq!(tail_click.len(), 1440, "Squelch tail click must be 1440 samples (60 ms @ 24 kHz)");
    
    let tail_click_inst = filter.squelch_tail();
    assert_eq!(tail_click_inst.len(), 1440);
    assert_eq!(VhfDspFilter::generate_squelch_tail(sample_rate).len(), 1440);

    for (i, &s) in tail_click.iter().enumerate() {
        assert!(s.is_finite(), "Squelch tail sample {} is not finite: {}", i, s);
        assert!(!s.is_nan(), "Squelch tail sample {} is NaN", i);
        assert!(s >= -1.0 && s <= 1.0, "Squelch tail sample {} clipped out of [-1.0, 1.0]: {}", i, s);
    }
    let tail_energy: f32 = tail_click.iter().map(|&s| s.abs()).sum();
    assert!(tail_energy > 0.1, "Squelch tail click must contain non-zero audio content");
}

#[test]
fn test_calculate_rms_silence_and_full_scale() {
    // Silence
    let silence = vec![0i16; 1024];
    assert_eq!(calculate_rms(&silence), 0.0);
    assert_eq!(calculate_rms(&[]), 0.0);

    // Full scale DC / square maximum
    let full_dc = vec![i16::MAX; 1024];
    let full_rms = calculate_rms(&full_dc);
    assert!(
        full_rms > 0.99 && full_rms <= 1.0,
        "Full scale DC RMS should be ~1.0, got {}",
        full_rms
    );

    // Full scale sine wave: amplitude ~ 32767 -> theoretical RMS = 1 / sqrt(2) ≈ 0.7071
    let sine_samples: Vec<i16> = (0..2400)
        .map(|i| {
            let angle = 2.0 * std::f32::consts::PI * 1000.0 * (i as f32 / 24000.0);
            (angle.sin() * 32767.0) as i16
        })
        .collect();
    let sine_rms = calculate_rms(&sine_samples);
    assert!(
        (sine_rms - 0.7071).abs() < 0.02,
        "Full scale sine RMS should be ~0.7071, got {}",
        sine_rms
    );
}

#[test]
fn test_vhf_dsp_filter_noise_and_process_sample() {
    let sample_rate = 24000;
    let mut filter = VhfDspFilter::new(sample_rate);
    assert!(filter.noise_gain() > 0.0);

    // Test process_sample
    let mut output_samples = Vec::new();
    for _ in 0..1000 {
        let out = filter.process_sample(0.0);
        assert!(out.is_finite());
        assert!(!out.is_nan());
        output_samples.push(out);
    }

    // With noise enabled (default ~ -30 dB or gain ~ 0.03), RMS of silence input should reflect noise
    let noise_rms = calculate_f32_rms(&output_samples);
    assert!(
        noise_rms > 0.005 && noise_rms < 0.1,
        "Noise RMS should be around -30 dB (gain ~0.03), got {}",
        noise_rms
    );

    // With noise disabled, silence should output near 0.0
    filter.set_noise_enabled(false);
    filter.reset();
    let mut quiet_samples = Vec::new();
    for _ in 0..1000 {
        let out = filter.process_sample(0.0);
        quiet_samples.push(out);
    }
    let quiet_rms = calculate_f32_rms(&quiet_samples);
    assert!(quiet_rms < 1e-6, "With noise disabled, silence in must yield 0.0, got {}", quiet_rms);
}

#[test]
fn test_audio_capture_mock_and_ringbuf() {
    let mut capture = AudioCapture::new_mock(24000);
    assert!(capture.is_capturing());

    // Push PCM samples into mock capture
    let test_pcm = vec![1000i16, 2000, 3000, -1000, -2000, -3000];
    capture.push_mock_samples(&test_pcm);

    // Test batch popping via pop_slice in read_samples
    let mut read_buf = vec![0i16; 10];
    let n = capture.read_samples(&mut read_buf);
    assert_eq!(n, 6);
    assert_eq!(&read_buf[..6], &test_pcm[..]);

    // Test read_all_samples batch read
    capture.push_mock_samples(&[111, 222, 333]);
    let all = capture.read_all_samples();
    assert_eq!(all, vec![111, 222, 333]);

    // Stopping capture
    capture.stop();
    assert!(!capture.is_capturing());

    // Verify push_mock_samples respects is_capturing (no samples added when stopped)
    capture.push_mock_samples(&[999i16, 888]);
    let mut empty_buf = vec![0i16; 10];
    let n2 = capture.read_samples(&mut empty_buf);
    assert_eq!(n2, 0, "No samples should be captured when capture is stopped");
}

#[test]
fn test_audio_playback_mock_lifecycle() {
    let mut playback = AudioPlayback::new_mock(24000);

    // Start ATC transmission -> triggers squelch open click
    playback.start_transmission();
    assert!(playback.is_transmitting());

    // Send ATC PCM chunk
    let speech_chunk = vec![5000i16; 480]; // 20 ms
    playback.play_chunk(&speech_chunk);

    // End transmission -> triggers squelch tail click
    playback.finish_transmission();
    assert!(!playback.is_transmitting());

    // Inspect collected output from mock sink
    let output = playback.get_played_samples();
    assert!(!output.is_empty(), "Playback sink should contain generated audio");
    // Check all output samples are finite
    for &s in &output {
        assert!(s.is_finite());
        assert!(!s.is_nan());
    }
}

#[test]
fn test_audio_playback_ring_buffer_overflow_warning() {
    // Create playback with a tiny 100-sample bounded ring buffer
    let (mut playback, mut consumer) = AudioPlayback::new_mock_with_buffer(24000, 100);

    // Squelch open produces 600 samples, which exceeds the 100-sample ring buffer
    // This triggers the warning and safely drops excess samples without panic
    playback.start_transmission();

    // Verify the consumer has captured up to the buffer capacity
    let mut drained = Vec::new();
    while let Some(s) = consumer.pop() {
        drained.push(s);
    }
    assert!(drained.len() <= 100);
    assert!(!drained.is_empty());
}
