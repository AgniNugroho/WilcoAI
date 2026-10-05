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

        let config = cpal::StreamConfig {
            channels: 1,
            sample_rate: cpal::SampleRate(sample_rate),
            buffer_size: cpal::BufferSize::Default,
        };

        let err_callback = |err| eprintln!("Audio capture stream error: {}", err);

        let is_cap_i16 = is_capturing.clone();
        let prod_i16 = Arc::clone(&producer);

        let stream = device
            .build_input_stream(
                &config,
                move |data: &[i16], _: &cpal::InputCallbackInfo| {
                    if is_cap_i16.load(Ordering::Relaxed) {
                        if let Ok(mut prod) = prod_i16.lock() {
                            prod.push_slice(data);
                        }
                    }
                },
                err_callback,
                None,
            )
            .or_else(|_| {
                let is_cap_f32 = is_capturing.clone();
                let prod_f32 = Arc::clone(&producer);
                device.build_input_stream(
                    &config,
                    move |data: &[f32], _: &cpal::InputCallbackInfo| {
                        if is_cap_f32.load(Ordering::Relaxed) {
                            if let Ok(mut prod) = prod_f32.lock() {
                                for &sample in data {
                                    let s16 = (sample.clamp(-1.0, 1.0) * 32767.0) as i16;
                                    let _ = prod.push(s16);
                                }
                            }
                        }
                    },
                    err_callback,
                    None,
                )
            })
            .map_err(|e| format!("Failed to create audio input stream: {}", e))?;

        stream
            .play()
            .map_err(|e| format!("Failed to start audio input stream: {}", e))?;

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
    pub fn push_mock_samples(&mut self, samples: &[i16]) {
        if let Some(ref mut prod) = self.mock_producer {
            prod.push_slice(samples);
        }
    }

    /// Reads up to `buf.len()` captured samples from the ring buffer into `buf`.
    /// Returns the number of samples copied.
    pub fn read_samples(&mut self, buf: &mut [i16]) -> usize {
        if let Some(ref mut cons) = self.consumer {
            let mut count = 0;
            for slot in buf.iter_mut() {
                if let Some(s) = cons.pop() {
                    *slot = s;
                    count += 1;
                } else {
                    break;
                }
            }
            count
        } else {
            0
        }
    }

    /// Reads all currently available samples from the ring buffer.
    pub fn read_all_samples(&mut self) -> Vec<i16> {
        let mut out = Vec::new();
        if let Some(ref mut cons) = self.consumer {
            while let Some(s) = cons.pop() {
                out.push(s);
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
