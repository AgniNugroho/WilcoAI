import React, { useState, useRef, useEffect } from 'react';
import { Terminal, Search, Radio, Headphones, Info, Trash2, ArrowDownCircle } from 'lucide-react';
import { TranscriptEntry } from '../types';

interface TranscriptLogProps {
  entries: TranscriptEntry[];
  onClear?: () => void;
}

export const TranscriptLog: React.FC<TranscriptLogProps> = ({ entries, onClear }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterSpeaker, setFilterSpeaker] = useState<'ALL' | 'PILOT' | 'ATC' | 'ATIS'>('ALL');
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries, autoScroll]);

  // Handle manual scroll to disable auto-scroll when user looks at past entries
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 40;
    if (isAtBottom !== autoScroll) {
      setAutoScroll(isAtBottom);
    }
  };

  const filteredEntries = entries.filter((entry) => {
    const matchesSearch =
      searchTerm.trim() === '' ||
      entry.text.toLowerCase().includes(searchTerm.toLowerCase()) ||
      entry.speaker.toLowerCase().includes(searchTerm.toLowerCase()) ||
      entry.radio.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesSpeaker =
      filterSpeaker === 'ALL' ||
      (filterSpeaker === 'PILOT' && entry.speaker === 'Pilot') ||
      (filterSpeaker === 'ATC' && entry.speaker === 'ATC') ||
      (filterSpeaker === 'ATIS' && entry.speaker === 'ATIS');

    return matchesSearch && matchesSpeaker;
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col h-full min-h-[420px]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3 mb-3">
        <div className="flex items-center gap-2.5">
          <Terminal className="w-5 h-5 text-emerald-400" />
          <span className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Aviation Communications Feed
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
            {filteredEntries.length} msgs
          </span>
        </div>

        {/* Filter Badges and Actions */}
        <div className="flex items-center gap-2">
          <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-[11px] font-semibold">
            {(['ALL', 'ATC', 'PILOT', 'ATIS'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setFilterSpeaker(filter)}
                className={`px-2 py-0.5 rounded transition-all ${
                  filterSpeaker === filter
                    ? 'bg-slate-800 text-emerald-400 font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {filter}
              </button>
            ))}
          </div>

          {onClear && (
            <button
              onClick={onClear}
              title="Clear transcript"
              className="p-1.5 rounded-lg bg-slate-950 border border-slate-800 text-slate-400 hover:text-rose-400 hover:border-rose-900 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Search Input Bar */}
      <div className="relative mb-3">
        <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Filter communications (e.g. 'taxi', 'cleared', 'wind', 'runway')..."
          className="w-full pl-9 pr-4 py-1.5 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50"
        />
      </div>

      {/* Scrollable Message Feed */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-slate-950"
      >
        {filteredEntries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center text-slate-500 space-y-2">
            <Radio className="w-8 h-8 opacity-40 text-emerald-400" />
            <p className="text-xs">No ATC transmissions recorded</p>
            <p className="text-[11px] text-slate-600">
              Press PTT to speak to Air Traffic Control on COM1 or COM2
            </p>
          </div>
        ) : (
          filteredEntries.map((entry) => {
            const isPilot = entry.speaker === 'Pilot';
            const isAtc = entry.speaker === 'ATC';

            return (
              <div
                key={entry.id}
                className={`p-3.5 rounded-xl border transition-all ${
                  isPilot
                    ? 'bg-slate-950/70 border-sky-500/30'
                    : isAtc
                    ? 'bg-slate-950/90 border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.05)]'
                    : 'bg-purple-950/20 border-purple-500/30'
                }`}
              >
                {/* Message Header */}
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    {isPilot ? (
                      <span className="flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-sky-500/20 text-sky-400 border border-sky-500/40">
                        <Radio className="w-3 h-3" />
                        PILOT
                      </span>
                    ) : isAtc ? (
                      <span className="flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                        <Headphones className="w-3 h-3" />
                        ATC CONTROLLER
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-purple-500/20 text-purple-400 border border-purple-500/40">
                        <Info className="w-3 h-3" />
                        ATIS BROADCAST
                      </span>
                    )}

                    <span className="font-mono text-[11px] text-slate-400 px-1.5 py-0.5 rounded bg-slate-800/80">
                      {entry.radio}
                    </span>

                    {entry.clearanceType && (
                      <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                        {entry.clearanceType}
                      </span>
                    )}
                  </div>

                  <span className="font-mono text-[10px] text-slate-500">
                    {entry.timestamp}
                  </span>
                </div>

                {/* Message Body */}
                <p
                  className={`text-xs font-mono leading-relaxed select-text ${
                    isPilot
                      ? 'text-sky-200'
                      : isAtc
                      ? 'text-emerald-200 font-medium'
                      : 'text-purple-200'
                  }`}
                >
                  {entry.text}
                </p>
              </div>
            );
          })
        )}
      </div>

      {/* Auto-scroll resume prompt */}
      {!autoScroll && (
        <div className="pt-2 flex justify-center">
          <button
            onClick={() => {
              setAutoScroll(true);
              if (scrollRef.current) {
                scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
              }
            }}
            className="flex items-center gap-1.5 px-3 py-1 bg-emerald-950/80 border border-emerald-500/40 rounded-full text-[11px] font-semibold text-emerald-300 shadow-md hover:bg-emerald-900 transition-colors"
          >
            <ArrowDownCircle className="w-3.5 h-3.5" />
            <span>Resume auto-scroll</span>
          </button>
        </div>
      )}
    </div>
  );
};
