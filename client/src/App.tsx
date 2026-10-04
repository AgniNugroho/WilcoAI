import { Radio, Mic, Volume2 } from 'lucide-react';

export default function App() {
  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 p-6">
      <header className="flex items-center justify-between border-b border-slate-800 pb-4 mb-6">
        <div className="flex items-center gap-3">
          <Radio className="w-6 h-6 text-emerald-400" />
          <h1 className="text-xl font-bold tracking-tight">Wilco AI Companion</h1>
        </div>
        <div className="flex items-center gap-2 text-xs bg-slate-800 px-3 py-1.5 rounded-full text-slate-300">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          Ready
        </div>
      </header>

      <main className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold uppercase text-slate-400 mb-4 tracking-wider">Radio Status</h2>
          <div className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-slate-950 rounded-lg border border-slate-800">
              <span className="text-sm text-slate-400">COM1 Active</span>
              <span className="font-mono text-emerald-400 font-bold text-lg">118.200</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-slate-950 rounded-lg border border-slate-800">
              <span className="text-sm text-slate-400">COM2 Active</span>
              <span className="font-mono text-slate-400 font-bold text-lg">121.650</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold uppercase text-slate-400 mb-4 tracking-wider">Audio & PTT</h2>
          <div className="space-y-4">
            <div className="flex items-center gap-3 p-3 bg-slate-950 rounded-lg">
              <Mic className="w-5 h-5 text-slate-400" />
              <div className="flex-1">
                <div className="text-xs text-slate-400 mb-1">Microphone Input</div>
                <div className="w-full bg-slate-800 rounded-full h-2">
                  <div className="bg-emerald-500 h-2 rounded-full w-0"></div>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-slate-950 rounded-lg">
              <Volume2 className="w-5 h-5 text-slate-400" />
              <div className="flex-1">
                <div className="text-xs text-slate-400 mb-1">ATC Audio Output</div>
                <div className="w-full bg-slate-800 rounded-full h-2">
                  <div className="bg-emerald-500 h-2 rounded-full w-0"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
