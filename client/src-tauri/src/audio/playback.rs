use super::dsp::VhfDspFilter;
use ringbuf::{HeapProducer, HeapRb};
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
    pub fn new(sample_rate: u32) -> Result<Self, String> {
        use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or_else(|| "No default output audio device found".to_string())?;

        let rb = HeapRb::<f32>::new(96000);
        let (producer, mut consumer) = rb.split();

        let config = cpal::StreamConfig {
            channels: 1,
            sample_rate: cpal::SampleRate(sample_rate),
            buffer_size: cpal::BufferSize::Default,
        };

        let err_callback = |err| eprintln!("Audio playback stream error: {}", err);

        let stream = device
            .build_output_stream(
                &config,
                move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                    for sample in data.iter_mut() {
                        *sample = consumer.pop().unwrap_or(0.0);
                    }
                },
                err_callback,
                None,
            )
            .map_err(|e| format!("Failed to create audio output stream: {}", e))?;

        stream
            .play()
            .map_err(|e| format!("Failed to start audio output stream: {}", e))?;

        Ok(Self {
            sample_rate,
            filter: VhfDspFilter::new(sample_rate),
            is_transmitting: false,
            mock_sink: None,
            producer: Some(producer),
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
    fn enqueue_samples(&mut self, samples: &[f32]) {
        if let Some(ref sink) = self.mock_sink {
            if let Ok(mut lock) = sink.lock() {
                lock.extend_from_slice(samples);
            }
        }
        if let Some(ref mut prod) = self.producer {
            prod.push_slice(samples);
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
