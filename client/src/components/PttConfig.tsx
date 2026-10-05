import React, { useState, useEffect, useRef } from 'react';
import { Gamepad2, Keyboard, Mouse, X, AlertCircle, Check, Sliders, RefreshCw } from 'lucide-react';
import { PttBinding, PttConfig as PttConfigType, RadioType } from '../types';

interface PttConfigProps {
  config: PttConfigType;
  isOpen: boolean;
  onClose: () => void;
  onSaveBinding: (radio: RadioType, binding: PttBinding) => Promise<void>;
  onStartLearning: (radio: RadioType) => Promise<void>;
  onStopLearning: () => Promise<void>;
}

export const PttConfig: React.FC<PttConfigProps> = ({
  config,
  isOpen,
  onClose,
  onSaveBinding,
  onStartLearning,
  onStopLearning,
}) => {
  const [learningRadio, setLearningRadio] = useState<RadioType | null>(null);
  const [activeTab, setActiveTab] = useState<RadioType>('Com1');
  const initialBindingRef = useRef<string | null>(null);

  // Human readable description of a binding
  const formatBindingText = (binding: PttBinding): string => {
    const parts: string[] = [];
    if (binding.joystick_button !== undefined && binding.joystick_button !== null) {
      parts.push(`Joystick Btn #${binding.joystick_button}`);
    }
    if (binding.mouse_button !== undefined && binding.mouse_button !== null) {
      const mouseName =
        binding.mouse_button === 4
          ? 'Mouse 4 (Thumb Back)'
          : binding.mouse_button === 5
          ? 'Mouse 5 (Thumb Forward)'
          : binding.mouse_button === 3
          ? 'Middle Mouse'
          : `Mouse Button #${binding.mouse_button}`;
      parts.push(mouseName);
    }
    if (binding.keyboard_key) {
      parts.push(`Key [${binding.keyboard_key}]`);
    }
    return parts.length > 0 ? parts.join(' | ') : 'No binding assigned';
  };

  // Automatically exit learning state when incoming config changes compared to initial snapshot
  useEffect(() => {
    if (!learningRadio || !initialBindingRef.current) return;
    const currentBindingStr = JSON.stringify(learningRadio === 'Com1' ? config.com1 : config.com2);
    if (currentBindingStr !== initialBindingRef.current) {
      initialBindingRef.current = null;
      setLearningRadio(null);
      onStopLearning();
    }
  }, [config, learningRadio, onStopLearning]);

  // Keyboard capture during learning mode
  useEffect(() => {
    if (!learningRadio) return;

    const handleKeyDown = async (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const keyName = e.code === 'Space' ? 'Space' : e.code;
      const target = learningRadio;
      initialBindingRef.current = null;
      setLearningRadio(null);

      await onSaveBinding(target, {
        joystick_button: null,
        mouse_button: null,
        keyboard_key: keyName,
      });
      await onStopLearning();
    };

    const handleMouseDown = async (e: MouseEvent) => {
      // Allow Mouse 3, 4, 5
      if (e.button === 1 || e.button === 3 || e.button === 4) {
        e.preventDefault();
        e.stopPropagation();

        const mouseBtn = e.button === 1 ? 3 : e.button === 3 ? 4 : 5;
        const target = learningRadio;
        initialBindingRef.current = null;
        setLearningRadio(null);

        await onSaveBinding(target, {
          joystick_button: null,
          mouse_button: mouseBtn,
          keyboard_key: null,
        });
        await onStopLearning();
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    window.addEventListener('mousedown', handleMouseDown, true);

    return () => {
      window.removeEventListener('keydown', handleKeyDown, true);
      window.removeEventListener('mousedown', handleMouseDown, true);
    };
  }, [learningRadio, onSaveBinding, onStopLearning]);

  if (!isOpen) return null;

  const currentBinding = activeTab === 'Com1' ? config.com1 : config.com2;

  const handleStartLearn = async (radio: RadioType) => {
    initialBindingRef.current = JSON.stringify(radio === 'Com1' ? config.com1 : config.com2);
    setLearningRadio(radio);
    await onStartLearning(radio);
  };

  const handleCancelLearn = async () => {
    initialBindingRef.current = null;
    setLearningRadio(null);
    await onStopLearning();
  };

  const handleClose = async () => {
    if (learningRadio) {
      initialBindingRef.current = null;
      setLearningRadio(null);
      await onStopLearning();
    }
    onClose();
  };

  const handleClear = async (radio: RadioType) => {
    await onSaveBinding(radio, {
      joystick_button: null,
      keyboard_key: null,
      mouse_button: null,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-400">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100">
                Push-To-Talk (PTT) Hardware Setup
              </h2>
              <p className="text-xs text-slate-400">
                Configure flight yoke, joystick, mouse, or keyboard transmit bindings
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Radio Selector Tabs */}
        <div className="flex border-b border-slate-800 bg-slate-950/50 p-2 gap-2">
          <button
            onClick={() => setActiveTab('Com1')}
            className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold tracking-wider transition-all flex items-center justify-center gap-2 ${
              activeTab === 'Com1'
                ? 'bg-slate-800 text-emerald-400 border border-emerald-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
            }`}
          >
            <span>COM1 Transceiver</span>
            {config.com1.joystick_button !== null ||
            config.com1.mouse_button !== null ||
            config.com1.keyboard_key ? (
              <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            ) : null}
          </button>

          <button
            onClick={() => setActiveTab('Com2')}
            className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold tracking-wider transition-all flex items-center justify-center gap-2 ${
              activeTab === 'Com2'
                ? 'bg-slate-800 text-cyan-400 border border-cyan-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-850'
            }`}
          >
            <span>COM2 Transceiver</span>
            {config.com2.joystick_button !== null ||
            config.com2.mouse_button !== null ||
            config.com2.keyboard_key ? (
              <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
            ) : null}
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5">
          {/* Active Binding Card */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Assigned {activeTab} Trigger Binding
            </span>
            <div className="font-mono text-base font-bold text-slate-100 flex items-center gap-2">
              <span className="p-1.5 bg-slate-800 rounded text-slate-300">
                {currentBinding.joystick_button !== null && currentBinding.joystick_button !== undefined ? (
                  <Gamepad2 className="w-4 h-4 text-emerald-400" />
                ) : currentBinding.mouse_button !== null && currentBinding.mouse_button !== undefined ? (
                  <Mouse className="w-4 h-4 text-sky-400" />
                ) : currentBinding.keyboard_key ? (
                  <Keyboard className="w-4 h-4 text-purple-400" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-slate-500" />
                )}
              </span>
              <span>{formatBindingText(currentBinding)}</span>
            </div>
          </div>

          {/* Learning Wizard Interactive Box */}
          {learningRadio === activeTab ? (
            <div className="p-5 rounded-xl bg-emerald-950/30 border border-emerald-500/50 flex flex-col items-center justify-center gap-3 text-center animate-pulse">
              <div className="p-3 bg-emerald-500/20 rounded-full text-emerald-400 animate-bounce">
                <RefreshCw className="w-6 h-6 animate-spin" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-emerald-300">
                  Learning Mode Active for {learningRadio}
                </h4>
                <p className="text-xs text-slate-300 mt-1 max-w-sm">
                  Press any flight stick trigger, gamepad button, mouse thumb button (Mouse 4/5), or keyboard key now.
                </p>
              </div>
              <button
                onClick={handleCancelLearn}
                className="mt-2 py-1.5 px-4 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 border border-slate-600"
              >
                Cancel Learning
              </button>
            </div>
          ) : (
            <div className="flex gap-3">
              <button
                onClick={() => handleStartLearn(activeTab)}
                className="flex-1 py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs tracking-wider flex items-center justify-center gap-2 transition-all shadow-md shadow-emerald-950"
              >
                <Gamepad2 className="w-4 h-4" />
                <span>LEARN BUTTON / KEY</span>
              </button>

              <button
                onClick={() => handleClear(activeTab)}
                className="py-3 px-4 rounded-xl bg-slate-800 hover:bg-slate-750 text-slate-300 font-semibold text-xs tracking-wider transition-all border border-slate-700"
              >
                Clear
              </button>
            </div>
          )}

          {/* Quick Presets Section */}
          <div className="space-y-2 pt-2 border-t border-slate-800/80">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Quick Input Presets
            </span>
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() =>
                  onSaveBinding(activeTab, {
                    joystick_button: null,
                    mouse_button: null,
                    keyboard_key: 'Space',
                  })
                }
                className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 hover:border-slate-700 text-left transition-all"
              >
                <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                  <Keyboard className="w-3.5 h-3.5 text-purple-400" />
                  Spacebar
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Keyboard Space</div>
              </button>

              <button
                onClick={() =>
                  onSaveBinding(activeTab, {
                    joystick_button: null,
                    mouse_button: 4,
                    keyboard_key: null,
                  })
                }
                className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 hover:border-slate-700 text-left transition-all"
              >
                <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                  <Mouse className="w-3.5 h-3.5 text-sky-400" />
                  Mouse 4
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Thumb Back</div>
              </button>

              <button
                onClick={() =>
                  onSaveBinding(activeTab, {
                    joystick_button: 0,
                    mouse_button: null,
                    keyboard_key: null,
                  })
                }
                className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 hover:border-slate-700 text-left transition-all"
              >
                <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                  <Gamepad2 className="w-3.5 h-3.5 text-emerald-400" />
                  Joystick #0
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Primary Trigger</div>
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 bg-slate-950/80 border-t border-slate-800 flex justify-end">
          <button
            onClick={handleClose}
            className="py-2 px-5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs tracking-wider flex items-center gap-2 transition-colors"
          >
            <Check className="w-4 h-4 text-emerald-400" />
            <span>DONE</span>
          </button>
        </div>
      </div>
    </div>
  );
};
