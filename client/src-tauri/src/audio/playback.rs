use super::dsp::VhfDspFilter;
use ringbuf::{HeapConsumer, HeapProducer, HeapRb};
use std::sync::{Arc, Mutex};

/// Plays incoming ATC speech chunks processed through the VHF DSP filter
/// with realistic squelch open clicks, radio bandpass, white noise, and squelch tail closure.
pub struct AudioPlayback {
    sample_rate: u32,
    filter: VhfDspFilter,
    is_transmitting: bool,
    mock_sink: Option<Arc<Mutex<Vec<f32>>>>,
    producer: Option<HeapProducer<f32>>,
    _stream: Option<cpal::Stream>,
}

impl AudioPlayback {
    /// Creates real audio playback output stream using cpal.
    /// Supports mono or multi-channel/stereo devices (duplicating mono to all channels).
    pub fn new(sample_rate: u32) -> Result<Self, String> {
        use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or_else(|| "No default output audio device found".to_string())?;

        let default_channels = device
            .default_output_config()
            .map(|c| c.channels())
            .unwrap_or(2);

        let channels_to_try: Vec<u16> = if default_channels > 1 {
            vec![default_channels, 1]
        } else {
            vec![1, 2]
        };

        let mut last_error = String::new();
        let mut active_stream: Option<cpal::Stream> = None;
        let mut active_producer: Option<HeapProducer<f32>> = None;

        for ch in channels_to_try {
            let config = cpal::StreamConfig {
                channels: ch,
                sample_rate: cpal::SampleRate(sample_rate),
                buffer_size: cpal::BufferSize::Default,
            };

            let err_callback = |err| eprintln!("Audio playback stream error: {}", err);
            let ch_usize = ch as usize;

            let rb = HeapRb::<f32>::new(96000);
            let (producer, mut consumer) = rb.split();

            let stream_res = if ch == 1 {
                // Direct mono playback
                device.build_output_stream(
                    &config,
                    move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                        let popped = consumer.pop_slice(data);
                        for i in popped..data.len() {
                            data[i] = 0.0;
                        }
                    },
                    err_callback,
                    None,
                )
            } else {
                // Stereo / multichannel playback: duplicate mono ATC speech to all channels
                let mut temp_buf = vec![0.0; 4096];
                device.build_output_stream(
                    &config,
                    move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                        let frames = data.len() / ch_usize;
                        if temp_buf.len() < frames {
                            temp_buf.resize(frames, 0.0);
                        }
                        let popped = consumer.pop_slice(&mut temp_buf[..frames]);
                        for (i, frame) in data.chunks_exact_mut(ch_usize).enumerate() {
                            let sample = if i < popped { temp_buf[i] } else { 0.0 };
                            for out in frame.iter_mut() {
                                *out = sample;
                            }
                        }
                    },
                    err_callback,
                    None,
                )
            };

            match stream_res {
                Ok(stream) => {
                    if let Err(e) = stream.play() {
                        last_error = format!("Failed to play output stream (channels={}): {}", ch, e);
                        continue;
                    }
                    active_stream = Some(stream);
                    active_producer = Some(producer);
                    break;
                }
                Err(e) => {
                    last_error = format!("Failed to build output stream (channels={}): {}", ch, e);
                }
            }
        }

        let stream = active_stream.ok_or_else(|| {
            format!("Failed to initialize audio playback device: {}", last_error)
        })?;

        Ok(Self {
            sample_rate,
            filter: VhfDspFilter::new(sample_rate),
            is_transmitting: false,
            mock_sink: None,
            producer: active_producer,
            _stream: Some(stream),
        })
    }

    /// Creates a mock AudioPlayback instance for unit testing and offline processing.
    pub fn new_mock(sample_rate: u32) -> Self {
        Self {
            sample_rate,
            filter: VhfDspFilter::new(sample_rate),
            is_transmitting: false,
            mock_sink: Some(Arc::new(Mutex::new(Vec::new()))),
            producer: None,
            _stream: None,
        }
    }

    /// Creates a mock AudioPlayback instance with a real bounded ring buffer to test buffer overflows.
    pub fn new_mock_with_buffer(sample_rate: u32, capacity: usize) -> (Self, HeapConsumer<f32>) {
        let rb = HeapRb::<f32>::new(capacity);
        let (producer, consumer) = rb.split();
        (
            Self {
                sample_rate,
                filter: VhfDspFilter::new(sample_rate),
                is_transmitting: false,
                mock_sink: Some(Arc::new(Mutex::new(Vec::new()))),
                producer: Some(producer),
                _stream: None,
            },
            consumer,
        )
    }

    /// Emits squelch open click and marks transmission as active.
    pub fn start_transmission(&mut self) {
        self.is_transmitting = true;
        let open_click = self.filter.squelch_open();
        self.enqueue_samples(&open_click);
    }

    /// Plays a chunk of 16-bit PCM speech audio processed through the VHF DSP filter.
    pub fn play_chunk(&mut self, chunk: &[i16]) {
        let mut float_chunk: Vec<f32> = chunk
            .iter()
            .map(|&s| s as f32 / 32768.0)
            .collect();
        self.filter.process_buffer(&mut float_chunk);
        self.enqueue_samples(&float_chunk);
    }

    /// Plays a chunk of 32-bit float speech audio processed through the VHF DSP filter.
    pub fn play_f32_chunk(&mut self, chunk: &[f32]) {
        let mut float_chunk = chunk.to_vec();
        self.filter.process_buffer(&mut float_chunk);
        self.enqueue_samples(&float_chunk);
    }

    /// Emits squelch tail click and marks transmission as concluded.
    pub fn finish_transmission(&mut self) {
        let tail_click = self.filter.squelch_tail();
        self.enqueue_samples(&tail_click);
        self.is_transmitting = false;
    }

    /// Internal helper to push samples to either real output stream or mock sink.
    /// Tracks ring buffer capacity and logs a warning on overflow drops.
    fn enqueue_samples(&mut self, samples: &[f32]) {
        if let Some(ref sink) = self.mock_sink {
            if let Ok(mut lock) = sink.lock() {
                lock.extend_from_slice(samples);
            }
        }
        if let Some(ref mut prod) = self.producer {
            let pushed = prod.push_slice(samples);
            if pushed < samples.len() {
                let dropped = samples.len() - pushed;
                eprintln!(
                    "Warning: AudioPlayback ring buffer overflow: dropped {} samples (pushed {}/{})",
                    dropped, pushed, samples.len()
                );
            }
        }
    }

    /// Returns whether ATC speech is currently transmitting.
    pub fn is_transmitting(&self) -> bool {
        self.is_transmitting
    }

    /// Retrieves all played samples from the mock sink for assertion and verification.
    pub fn get_played_samples(&self) -> Vec<f32> {
        if let Some(ref sink) = self.mock_sink {
            if let Ok(lock) = sink.lock() {
                return lock.clone();
            }
        }
        Vec::new()
    }

    /// Returns a reference to the inner VHF DSP filter.
    pub fn filter(&self) -> &VhfDspFilter {
        &self.filter
    }

    /// Returns a mutable reference to the inner VHF DSP filter.
    pub fn filter_mut(&mut self) -> &mut VhfDspFilter {
        &mut self.filter
    }

    /// Returns configured sample rate in Hz.
    pub fn sample_rate(&self) -> u32 {
        self.sample_rate
    }
}
