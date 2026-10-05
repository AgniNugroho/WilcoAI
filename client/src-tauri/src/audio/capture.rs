use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use ringbuf::{HeapConsumer, HeapProducer, HeapRb};

/// Audio capture subsystem capturing mono 16-bit PCM microphone input
/// into a lock-free SPSC ring buffer for speech transmission to the ATC gateway.
pub struct AudioCapture {
    sample_rate: u32,
    is_capturing: Arc<AtomicBool>,
    consumer: Option<HeapConsumer<i16>>,
    mock_producer: Option<HeapProducer<i16>>,
    _stream: Option<cpal::Stream>,
}

impl AudioCapture {
    /// Creates a real audio capture stream using cpal on the default input device.
    /// Supports mono or multi-channel/stereo devices (downmixing stereo/multi-channel to mono).
    pub fn new(sample_rate: u32) -> Result<Self, String> {
        use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

        let host = cpal::default_host();
        let device = host
            .default_input_device()
            .ok_or_else(|| "No default input audio device found".to_string())?;

        let rb = HeapRb::<i16>::new(96000); // 4-second buffer at 24 kHz
        let (producer, consumer) = rb.split();
        let producer = Arc::new(Mutex::new(producer));
        let is_capturing = Arc::new(AtomicBool::new(true));

        let default_channels = device
            .default_input_config()
            .map(|c| c.channels())
            .unwrap_or(1);

        let channels_to_try: Vec<u16> = if default_channels > 1 {
            vec![default_channels, 1]
        } else {
            vec![1, 2]
        };

        let mut last_error = String::new();
        let mut active_stream: Option<cpal::Stream> = None;

        for ch in channels_to_try {
            let config = cpal::StreamConfig {
                channels: ch,
                sample_rate: cpal::SampleRate(sample_rate),
                buffer_size: cpal::BufferSize::Default,
            };

            let err_callback = |err| eprintln!("Audio capture stream error: {}", err);
            let is_cap = is_capturing.clone();
            let prod = Arc::clone(&producer);

            let stream_res = if ch == 1 {
                // Direct mono capture
                let is_cap_mono = is_cap.clone();
                let prod_mono = Arc::clone(&prod);
                device
                    .build_input_stream(
                        &config,
                        move |data: &[i16], _: &cpal::InputCallbackInfo| {
                            if is_cap_mono.load(Ordering::Relaxed) {
                                if let Ok(mut p) = prod_mono.lock() {
                                    p.push_slice(data);
                                }
                            }
                        },
                        err_callback,
                        None,
                    )
                    .or_else(|_| {
                        let is_cap_f32 = is_cap.clone();
                        let prod_f32 = Arc::clone(&prod);
                        device.build_input_stream(
                            &config,
                            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                                if is_cap_f32.load(Ordering::Relaxed) {
                                    if let Ok(mut p) = prod_f32.lock() {
                                        for &sample in data {
                                            let s16 = (sample.clamp(-1.0, 1.0) * 32767.0) as i16;
                                            let _ = p.push(s16);
                                        }
                                    }
                                }
                            },
                            err_callback,
                            None,
                        )
                    })
            } else {
                // Stereo / multichannel downmix to mono: (left + right) / 2
                let ch_usize = ch as usize;
                let is_cap_stereo = is_cap.clone();
                let prod_stereo = Arc::clone(&prod);
                device
                    .build_input_stream(
                        &config,
                        move |data: &[i16], _: &cpal::InputCallbackInfo| {
                            if is_cap_stereo.load(Ordering::Relaxed) {
                                if let Ok(mut p) = prod_stereo.lock() {
                                    for frame in data.chunks_exact(ch_usize) {
                                        let sum: i32 = frame.iter().map(|&s| s as i32).sum();
                                        let mono = (sum / ch as i32) as i16;
                                        let _ = p.push(mono);
                                    }
                                }
                            }
                        },
                        err_callback,
                        None,
                    )
                    .or_else(|_| {
                        let is_cap_f32 = is_cap.clone();
                        let prod_f32 = Arc::clone(&prod);
                        device.build_input_stream(
                            &config,
                            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                                if is_cap_f32.load(Ordering::Relaxed) {
                                    if let Ok(mut p) = prod_f32.lock() {
                                        for frame in data.chunks_exact(ch_usize) {
                                            let sum: f32 = frame.iter().copied().sum();
                                            let mono_f32 = sum / ch as f32;
                                            let s16 = (mono_f32.clamp(-1.0, 1.0) * 32767.0) as i16;
                                            let _ = p.push(s16);
                                        }
                                    }
                                }
                            },
                            err_callback,
                            None,
                        )
                    })
            };

            match stream_res {
                Ok(stream) => {
                    if let Err(e) = stream.play() {
                        last_error = format!("Failed to play capture stream (channels={}): {}", ch, e);
                        continue;
                    }
                    active_stream = Some(stream);
                    break;
                }
                Err(e) => {
                    last_error = format!("Failed to build capture stream (channels={}): {}", ch, e);
                }
            }
        }

        let stream = active_stream.ok_or_else(|| {
            format!("Failed to initialize audio capture device: {}", last_error)
        })?;

        Ok(Self {
            sample_rate,
            is_capturing,
            consumer: Some(consumer),
            mock_producer: None,
            _stream: Some(stream),
        })
    }

    /// Creates a mock AudioCapture instance for unit and headless testing.
    pub fn new_mock(sample_rate: u32) -> Self {
        let rb = HeapRb::<i16>::new(48000);
        let (prod, cons) = rb.split();
        Self {
            sample_rate,
            is_capturing: Arc::new(AtomicBool::new(true)),
            consumer: Some(cons),
            mock_producer: Some(prod),
            _stream: None,
        }
    }

    /// Pushes PCM samples into the mock capture buffer.
    /// Only accepts samples if capturing is actively enabled.
    pub fn push_mock_samples(&mut self, samples: &[i16]) {
        if !self.is_capturing() {
            return;
        }
        if let Some(ref mut prod) = self.mock_producer {
            prod.push_slice(samples);
        }
    }

    /// Reads up to `buf.len()` captured samples from the ring buffer into `buf` using batch popping.
    /// Returns the number of samples copied.
    pub fn read_samples(&mut self, buf: &mut [i16]) -> usize {
        if let Some(ref mut cons) = self.consumer {
            cons.pop_slice(buf)
        } else {
            0
        }
    }

    /// Reads all currently available samples from the ring buffer in batches.
    pub fn read_all_samples(&mut self) -> Vec<i16> {
        let mut out = Vec::new();
        if let Some(ref mut cons) = self.consumer {
            let mut temp = [0i16; 512];
            loop {
                let n = cons.pop_slice(&mut temp);
                if n == 0 {
                    break;
                }
                out.extend_from_slice(&temp[..n]);
            }
        }
        out
    }

    /// Returns whether the capture stream is currently active.
    pub fn is_capturing(&self) -> bool {
        self.is_capturing.load(Ordering::SeqCst)
    }

    /// Pauses audio capture.
    pub fn stop(&mut self) {
        self.is_capturing.store(false, Ordering::SeqCst);
    }

    /// Resumes audio capture.
    pub fn start(&mut self) {
        self.is_capturing.store(true, Ordering::SeqCst);
    }

    /// Returns configured sample rate in Hz.
    pub fn sample_rate(&self) -> u32 {
        self.sample_rate
    }
}
