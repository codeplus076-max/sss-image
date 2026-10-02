import React, { useState, useEffect } from 'react';
import { Layers, Sliders, Volume2, VolumeX, ArrowUpRight, FileSpreadsheet } from 'lucide-react';
import { soundFx } from '../utils/audio';
import { API_BASE_URL } from '../services/api';

export default function TopAppBar({ 
  currentView, 
  onSwitchView, 
  onToggleLayerDrawer, 
  onOpenSensorTuner, 
  anomalyCount,
  surveyFile,
  onOpenLegal,
  backendHealth
}) {
  const [isMuted, setIsMuted] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);

  // Detect scroll to transition from fully integrated transparent glass to subtle opaque glass
  useEffect(() => {
    const handleScroll = (e) => {
      const scrollY = window.scrollY || (e.target && e.target.scrollTop) || 0;
      setIsScrolled(scrollY > 10);
    };

    window.addEventListener('scroll', handleScroll, { capture: true, passive: true });
    return () => window.removeEventListener('scroll', handleScroll, { capture: true });
  }, []);

  const handleMuteToggle = () => {
    const muted = soundFx.toggleMute();
    setIsMuted(muted);
    if (!muted) {
      soundFx.playSonarPing(1350, 0.5);
    }
  };

  const navItems = [
    { id: 'view-hero', label: 'Overview' },
    { id: 'view-ingest', label: 'Ingest' },
    { id: 'view-quality', label: 'Quality' },
    { id: 'view-detections', label: 'Detection', badge: anomalyCount },
    { id: 'view-workspace', label: 'Evidence' },
    { id: 'view-summary', label: 'Report' },
  ];

  return (
    <header 
      className={`fixed top-0 inset-x-0 z-50 h-14 flex items-center justify-between px-4 sm:px-6 lg:px-8 select-none transition-all duration-300 ${
        isScrolled
          ? 'bg-[#040812]/85 backdrop-blur-md border-b border-white/[0.08] shadow-[0_4px_24px_rgba(0,0,0,0.4)]'
          : 'bg-[#040812]/40 backdrop-blur-sm border-b border-white/[0.04]'
      }`}
    >
      {/* ======================================================== */}
      {/* 1. BRAND & SURVEY WORKSPACE IDENTITY                     */}
      {/* ======================================================== */}
      <div className="flex items-center space-x-3 shrink-0">
        <button 
          onClick={() => {
            soundFx.playSonarPing(1400, 0.4);
            onSwitchView('view-hero');
          }}
          className="flex items-center space-x-3 text-left focus:outline-none group cursor-pointer"
        >
          {/* Restrained Instrument Reticle Mark */}
          <div className="w-5 h-5 border border-[#22354e]/80 rounded-sm flex items-center justify-center bg-[#07101d]/60 group-hover:border-primary/60 transition-colors">
            <div className="w-1.5 h-1.5 rounded-full bg-primary/90"></div>
          </div>

          <div className="flex flex-col">
            <span className="text-sm font-sans font-semibold tracking-[0.16em] text-[#f8fafc] uppercase group-hover:text-primary transition-colors">
              SONAROPS
            </span>
            <span className="text-[11px] font-sans text-[#7d93ad] tracking-tight -mt-0.5">
              Survey Workspace
            </span>
          </div>
        </button>
      </div>

      {/* ======================================================== */}
      {/* 2. NATURAL & EDITORIAL NAVIGATION (NO PILL SHAPES)       */}
      {/* ======================================================== */}
      <nav className="hidden md:flex items-center space-x-1 lg:space-x-1.5">
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              id={`nav-${item.id}`}
              onClick={() => {
                soundFx.playSonarPing(isActive ? 1100 : 1300, 0.35);
                onSwitchView(item.id);
              }}
              className={`relative h-14 flex items-center px-3 lg:px-3.5 text-xs tracking-wide transition-colors duration-200 cursor-pointer ${
                isActive
                  ? 'text-[#f8fafc] font-medium bg-white/[0.03]'
                  : 'text-[#8ea4bf] hover:text-[#f8fafc] hover:bg-white/[0.015]'
              }`}
            >
              <span>{item.label}</span>
              {Boolean(item.badge && item.badge > 0) && (
                <span className="ml-1.5 font-mono text-[9px] text-amber-400 bg-amber-500/10 border border-amber-500/30 px-1 py-0.2 rounded-sm">
                  {item.badge}
                </span>
              )}

              {/* Subtle Cyan Bottom Line Indicator */}
              {isActive && (
                <span className="absolute bottom-0 inset-x-2 h-[2px] bg-primary rounded-full transition-all duration-300" />
              )}
            </button>
          );
        })}
      </nav>

      {/* ======================================================== */}
      {/* 3. ACTIVE DATASET / REAL STATE & UTILITIES               */}
      {/* ======================================================== */}
      <div className="flex items-center space-x-2 sm:space-x-3">
        {/* Real Dataset File Status Badge */}
        <div className="hidden xl:flex items-center space-x-2 font-mono text-[10px] px-2.5 py-1 rounded-sm bg-[#09111e]/70 border border-[#1b2a3f] text-[#8ea4bf]">
          <span className="text-[#50637c]">DATASET:</span>
          {surveyFile && surveyFile.name ? (
            <span className="text-[#cbd5e1] font-medium max-w-[140px] truncate" title={surveyFile.name}>
              {surveyFile.name}
            </span>
          ) : (
            <span className="text-[#64748b] italic">AWAITING DATA</span>
          )}
        </div>

        {/* Backend API Connection Status Badge */}
        <div 
          className="hidden sm:flex items-center space-x-1.5 font-mono text-[10px] px-2 py-1 rounded-sm bg-[#09111e]/70 border border-[#1b2a3f] text-[#8ea4bf]"
          title={
            backendHealth?.connected 
              ? `Backend API operational (${API_BASE_URL})` 
              : backendHealth?.status === 'waking'
                ? `Waking up Render backend container (attempt ${backendHealth?.retry || 1}/8)...`
                : `Backend API offline (${API_BASE_URL})`
          }
        >
          <span 
            className={`w-1.5 h-1.5 rounded-full ${
              backendHealth?.connected 
                ? 'bg-primary shadow-[0_0_6px_rgba(45,212,191,0.6)]' 
                : backendHealth?.status === 'waking'
                  ? 'bg-amber-400 animate-ping'
                  : 'bg-amber-400'
            }`}
          ></span>
          <span className="text-[#50637c]">API:</span>
          <span className={backendHealth?.connected ? 'text-primary font-medium' : 'text-amber-400 font-medium'}>
            {backendHealth?.connected ? 'ONLINE' : backendHealth?.status === 'waking' ? 'WAKING UP...' : 'OFFLINE'}
          </span>
        </div>

        {/* Audio Mute/Unmute */}
        <button
          onClick={handleMuteToggle}
          title={isMuted ? "Unmute Acoustic Signals" : "Mute Acoustic Signals"}
          className={`w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center border rounded-sm transition-colors cursor-pointer ${
            isMuted 
              ? 'border-[#1b283d] bg-[#080d16]/70 text-[#64748b] hover:text-on-surface' 
              : 'border-[#22354e]/80 bg-[#0c1422]/70 text-primary hover:border-primary/60'
          }`}
        >
          {isMuted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
        </button>

        {/* Cartographic Layers Drawer */}
        <button
          onClick={() => {
            soundFx.playSonarPing(1100, 0.35);
            onToggleLayerDrawer();
          }}
          title="Cartographic Layers"
          className="w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center border border-[#1b283d] rounded-sm bg-[#0c1422]/70 text-[#8ea4bf] hover:text-on-surface hover:border-[#2a3c56] transition-colors cursor-pointer"
        >
          <Layers className="w-3.5 h-3.5" />
        </button>

        {/* Sensor Calibration Tuner */}
        <button
          onClick={() => {
            soundFx.playSonarPing(1200, 0.35);
            onOpenSensorTuner();
          }}
          title="Sensor Calibration"
          className="w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center border border-[#1b283d] rounded-sm bg-[#0c1422]/70 text-[#8ea4bf] hover:text-on-surface hover:border-[#2a3c56] transition-colors cursor-pointer"
        >
          <Sliders className="w-3.5 h-3.5" />
        </button>

        {/* Legal / Policy Documentation Access */}
        {onOpenLegal && (
          <button
            onClick={() => {
              soundFx.playSonarPing(1150, 0.3);
              onOpenLegal();
            }}
            title="Privacy Policy & Terms"
            className="hidden lg:flex items-center space-x-1 text-[11px] font-mono text-[#7d93ad] hover:text-[#f8fafc] px-2 py-1 rounded-sm border border-[#1b283d] hover:border-[#2a3c56] bg-[#0c1422]/50 transition-colors cursor-pointer"
          >
            <span>Legal</span>
          </button>
        )}
      </div>
    </header>
  );
}
