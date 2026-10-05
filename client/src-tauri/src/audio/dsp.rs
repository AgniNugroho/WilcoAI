use biquad::{Biquad, Coefficients, DirectForm2Transposed, Hertz, Type, Q_BUTTERWORTH_F32};

/// Calculates normalized RMS energy (0.0 .. 1.0) of 16-bit PCM audio samples for VU meter display.
pub fn calculate_rms(samples: &[i16]) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }
    let sum_sq: f64 = samples
        .iter()
        .map(|&s| {
            let norm = s as f64 / 32768.0;
            norm * norm
        })
        .sum();
    let mean_sq = sum_sq / (samples.len() as f64);
    (mean_sq.sqrt() as f32).clamp(0.0, 1.0)
}

/// Generates a squelch open click (25 ms) characteristic of VHF aviation radio transceivers.
pub fn generate_squelch_open(sample_rate: u32) -> Vec<f32> {
    let n = (sample_rate as f64 * 0.025).round() as usize;
    let mut samples = Vec::with_capacity(n);
    let mut rng = 0x87654321u32;
    for i in 0..n {
        let t = i as f32 / sample_rate as f32;
        // Xorshift32 PRNG for band noise
        rng ^= rng << 13;
        rng ^= rng >> 17;
        rng ^= rng << 5;
        let noise = (rng as f32 / 2147483648.0) - 1.0;

        // Damped resonant transient: 1.5 kHz pulse + rapid decay noise
        let env = (-t / 0.005).exp();
        let tone = (2.0 * std::f32::consts::PI * 1500.0 * t).sin() * 0.35 * env;
        let burst = noise * 0.15 * env;
        let sample = (tone + burst).clamp(-1.0, 1.0);
        samples.push(sample);
    }
    samples
}

/// Generates a squelch tail click (60 ms) representing carrier cutoff static burst.
pub fn generate_squelch_tail(sample_rate: u32) -> Vec<f32> {
    let n = (sample_rate as f64 * 0.060).round() as usize;
    let mut samples = Vec::with_capacity(n);
    let mut rng = 0x54321098u32;
    for i in 0..n {
        let t = i as f32 / sample_rate as f32;
        rng ^= rng << 13;
        rng ^= rng >> 17;
        rng ^= rng << 5;
        let noise = (rng as f32 / 2147483648.0) - 1.0;

        // Static hiss burst with abrupt closure transient
        let noise_env = if t < 0.045 {
            0.22
        } else {
            0.22 * (-(t - 0.045) / 0.004).exp()
        };
        let cutoff_pop = if (0.044..0.049).contains(&t) {
            -0.25 * (-(t - 0.044) / 0.002).exp()
        } else {
            0.0
        };
        let sample = (noise * noise_env + cutoff_pop).clamp(-1.0, 1.0);
        samples.push(sample);
    }
    samples
}

/// VHF radio DSP audio filter simulating communication transceivers.
/// Includes 4th-order cascaded biquad bandpass filter (~300 Hz to ~3200 Hz),
/// white noise generator (-30 dB), and squelch click generation.
pub struct VhfDspFilter {
    sample_rate: u32,
    hp1: DirectForm2Transposed<f32>,
    hp2: DirectForm2Transposed<f32>,
    lp1: DirectForm2Transposed<f32>,
    lp2: DirectForm2Transposed<f32>,
    noise_enabled: bool,
    noise_gain: f32,
    rng_state: u32,
}

impl VhfDspFilter {
    /// Creates a new VHF DSP filter configured for the given sample rate (e.g. 24000 Hz).
    pub fn new(sample_rate: u32) -> Self {
        let fs = Hertz::<f32>::from_hz(sample_rate as f32)
            .unwrap_or(Hertz::<f32>::from_hz(24000.0).unwrap());
        let hp_f0 = Hertz::<f32>::from_hz(300.0).unwrap();
        let lp_f0 = Hertz::<f32>::from_hz(3200.0).unwrap();

        let hp_coeffs =
            Coefficients::<f32>::from_params(Type::HighPass, fs, hp_f0, Q_BUTTERWORTH_F32)
                .expect("Valid high-pass filter coefficients");
        let lp_coeffs =
            Coefficients::<f32>::from_params(Type::LowPass, fs, lp_f0, Q_BUTTERWORTH_F32)
                .expect("Valid low-pass filter coefficients");

        Self {
            sample_rate,
            hp1: DirectForm2Transposed::<f32>::new(hp_coeffs),
            hp2: DirectForm2Transposed::<f32>::new(hp_coeffs),
            lp1: DirectForm2Transposed::<f32>::new(lp_coeffs),
            lp2: DirectForm2Transposed::<f32>::new(lp_coeffs),
            noise_enabled: true,
            noise_gain: 0.03, // ~ -30.4 dB
            rng_state: 0x12345678,
        }
    }

    /// Builder method to toggle background white noise.
    pub fn with_noise(mut self, enabled: bool) -> Self {
        self.noise_enabled = enabled;
        self
    }

    /// Enables or disables VHF background white noise.
    pub fn set_noise_enabled(&mut self, enabled: bool) {
        self.noise_enabled = enabled;
    }

    /// Returns whether background noise is currently enabled.
    pub fn noise_enabled(&self) -> bool {
        self.noise_enabled
    }

    /// Sets the background noise linear gain (default 0.03 = -30 dB).
    pub fn set_noise_gain(&mut self, gain: f32) {
        self.noise_gain = gain.max(0.0);
    }

    /// Returns the current background noise linear gain.
    pub fn noise_gain(&self) -> f32 {
        self.noise_gain
    }

    /// Returns the filter sample rate in Hz.
    pub fn sample_rate(&self) -> u32 {
        self.sample_rate
    }

    #[inline]
    fn next_random(&mut self) -> f32 {
        let mut x = self.rng_state;
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        self.rng_state = x;
        (x as f32 / 2147483648.0) - 1.0
    }

    /// Processes a single audio sample through the cascaded biquad filters and noise mixer.
    pub fn process_sample(&mut self, sample: f32) -> f32 {
        let s1 = self.hp1.run(sample);
        let s2 = self.hp2.run(s1);
        let s3 = self.lp1.run(s2);
        let s4 = self.lp2.run(s3);

        let out = if self.noise_enabled {
            s4 + self.next_random() * self.noise_gain
        } else {
            s4
        };
        out.clamp(-1.0, 1.0)
    }

    /// Processes a buffer of samples in place.
    pub fn process_buffer(&mut self, samples: &mut [f32]) {
        for s in samples.iter_mut() {
            *s = self.process_sample(*s);
        }
    }

    /// Resets the internal biquad delay states.
    pub fn reset(&mut self) {
        self.hp1.reset_state();
        self.hp2.reset_state();
        self.lp1.reset_state();
        self.lp2.reset_state();
    }

    /// Generates squelch open click for this filter's configured sample rate.
    pub fn squelch_open(&self) -> Vec<f32> {
        generate_squelch_open(self.sample_rate)
    }

    /// Generates squelch tail click for this filter's configured sample rate.
    pub fn squelch_tail(&self) -> Vec<f32> {
        generate_squelch_tail(self.sample_rate)
    }

    /// Associated function to generate squelch open click at any sample rate.
    pub fn generate_squelch_open(sample_rate: u32) -> Vec<f32> {
        generate_squelch_open(sample_rate)
    }

    /// Associated function to generate squelch tail click at any sample rate.
    pub fn generate_squelch_tail(sample_rate: u32) -> Vec<f32> {
        generate_squelch_tail(sample_rate)
    }
}
