import React, { useState, useEffect } from 'react';
import { 
  CheckCircle2, 
  AlertTriangle, 
  ArrowRight, 
  Filter, 
  Layers, 
  Eye, 
  Check, 
  Info,
  ShieldCheck,
  Crosshair,
  RefreshCw,
  Sliders
} from 'lucide-react';
import { soundFx } from '../../utils/audio';
import { MASTER_DETECTIONS } from '../../data/sharedDetections';

export default function DetectionsView({ 
  onNavigate,
  surveyFile,
  selectedAnomalyId,
  onSelectAnomaly,
  anomalies = [],
  analysisResult = null,
  isAnalyzing = false,
  analysisError = null,
  onRunAnalysis,
  evidenceUrl = null
}) {
  const [detections, setDetections] = useState(() => (
    anomalies && anomalies.length > 0 ? anomalies : []
  ));
  const [selectedId, setSelectedId] = useState(selectedAnomalyId || (anomalies && anomalies.length > 0 ? anomalies[0].id : null));
  const [hoveredId, setHoveredId] = useState(null);
  const [imageUrl, setImageUrl] = useState(null);
  const [confidenceCutoff, setConfidenceCutoff] = useState(20);
  const [targetModel, setTargetModel] = useState('all');

  const handleTriggerReanalysis = (overrideConf) => {
    if (!onRunAnalysis || !surveyFile || isAnalyzing) return;
    const finalCutoff = overrideConf != null ? overrideConf : confidenceCutoff;
    if (overrideConf != null) {
      setConfidenceCutoff(overrideConf);
    }
    soundFx.playSonarPing(1350, 0.4);
    onRunAnalysis(surveyFile, {
      confidence: finalCutoff / 100,
      selected_models: targetModel === 'all' ? undefined : [targetModel]
    });
  };

  // Sync detections whenever anomalies prop changes
  useEffect(() => {
    if (anomalies) {
      setDetections(anomalies);
      if (anomalies.length > 0) {
        if (!selectedId || !anomalies.some(d => d.id === selectedId)) {
          setSelectedId(anomalies[0].id);
        }
      } else {
        setSelectedId(null);
      }
    }
  }, [anomalies]);

  useEffect(() => {
    if (selectedAnomalyId) {
      setSelectedId(selectedAnomalyId);
    }
  }, [selectedAnomalyId]);

  useEffect(() => {
    if (surveyFile && (surveyFile instanceof File || surveyFile instanceof Blob)) {
      const url = URL.createObjectURL(surveyFile);
      setImageUrl(url);
      return () => URL.revokeObjectURL(url);
    } else if (evidenceUrl) {
      setImageUrl(evidenceUrl);
    } else if (analysisResult?.analysis_id) {
      setImageUrl(`${API_BASE_URL}/api/v1/analysis/${analysisResult.analysis_id}/evidence`);
    } else {
      setImageUrl(null);
    }
  }, [surveyFile, evidenceUrl, analysisResult]);

  const activeDetection = detections.find(d => d.id === selectedId) || detections[0] || null;

  const handleSelectDetection = (det) => {
    soundFx.playTargetLock();
    setSelectedId(det.id);
    if (onSelectAnomaly) {
      onSelectAnomaly(det.id);
    }
  };

  const handleToggleStatus = (id, e) => {
    e.stopPropagation();
    soundFx.playSonarPing(1200, 0.3);
    setDetections(prev => prev.map(item => {
      if (item.id === id) {
        return {
          ...item,
          status: item.status === 'VERIFIED' ? 'REVIEW' : 'VERIFIED'
        };
      }
      return item;
    }));
  };

  const handleContinueToGeolocation = () => {
    soundFx.playTargetLock();
    if (onNavigate) {
      onNavigate('view-workspace');
    }
  };

  const totalDetections = detections.length;
  const highConfidenceCount = detections.filter(d => (d.confidence || 0) >= 80).length;
  const reviewRequiredCount = detections.filter(d => d.status === 'REVIEW' || d.status === 'PENDING REVIEW').length;
  const filteredCount = analysisResult?.summary?.filtered_clutter ?? 0;

  return (
    <section className="relative w-full h-[calc(100vh-3.5rem)] overflow-y-auto bg-[#060911] text-[#f1f5f9] select-none p-4 sm:p-6 lg:p-8">
      <div className="max-w-7xl mx-auto space-y-5 pb-16">
        
        {/* ======================================================== */}
        {/* 1. HEADER & WORKFLOW SEQUENCE                            */}
        {/* ======================================================== */}
        <div className="border-b border-[#162234] pb-4 flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2 mb-1">
              <span className="w-1.5 h-1.5 rounded-sm bg-primary"></span>
              <span className="font-mono text-xs tracking-[0.2em] text-[#8ea4bf] uppercase font-semibold">
                03 — AI DETECTION
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-headline tracking-tight text-on-surface font-normal">
              Find what shouldn't be there.
            </h1>
            <p className="font-sans text-xs sm:text-sm text-[#94a3b8] max-w-xl mt-1 font-normal leading-relaxed">
              Screen acoustic imagery for anthropogenic anomalies, debris, and benthic obstacles.
            </p>
          </div>

          <div className="flex items-center space-x-2 font-mono text-[10px] text-[#64748b] shrink-0">
            <button 
              onClick={() => onNavigate && onNavigate('view-ingest')}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              01 INGEST
            </button>
            <span className="text-[#33465e]">→</span>
            <button 
              onClick={() => onNavigate && onNavigate('view-quality')}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              02 QUALITY
            </button>
            <span className="text-[#33465e]">→</span>
            <span className="text-primary font-semibold bg-[#101b2c] px-2 py-0.5 rounded-sm border border-[#22354e]">
              03 DETECTION
            </span>
            <span className="text-[#33465e]">→</span>
            <span className="text-[#50637c]">04 EVIDENCE</span>
          </div>
        </div>

        {/* Dynamic Status Banner: Error / Loading / Live Record / Demo */}
        {analysisError ? (
          <div className="flex items-center justify-between p-3 bg-red-950/40 border border-red-500/40 rounded-sm text-xs font-mono text-red-200">
            <div className="flex items-center space-x-2.5">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
              <div>
                <span className="font-bold text-red-300">VALIDATION REJECTED: </span>
                <span>{analysisError}</span>
              </div>
            </div>
            {onRunAnalysis && surveyFile && (
              <button
                onClick={() => onRunAnalysis(surveyFile)}
                disabled={isAnalyzing}
                className="px-2.5 py-1 bg-red-900/60 hover:bg-red-800/80 border border-red-500/50 text-white rounded-sm transition-colors text-[10px] font-semibold cursor-pointer shrink-0 ml-2 flex items-center space-x-1"
              >
                <RefreshCw className="w-3 h-3" />
                <span>Retry</span>
              </button>
            )}
          </div>
        ) : isAnalyzing ? (
          <div className="flex items-center justify-between p-3 bg-[#0b1d2e] border border-primary/40 rounded-sm text-xs font-mono text-cyan-200 animate-pulse">
            <div className="flex items-center space-x-2.5">
              <div className="w-3.5 h-3.5 rounded-full border-2 border-primary border-t-transparent animate-spin shrink-0"></div>
              <div>
                <span className="font-bold text-primary">RUNNING AI INFERENCE · </span>
                <span>Screening acoustic backscatter across verified multi-model pipeline...</span>
              </div>
            </div>
            <span className="text-[10px] text-primary/80 hidden sm:inline">PROCESSING SWATH</span>
          </div>
        ) : analysisResult ? (
          <div className="flex items-center justify-between p-2.5 bg-[#0b111e] border border-[#1a2638] rounded-sm text-xs font-mono text-[#8ea4bf]">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-3.5 h-3.5 text-primary shrink-0" />
              <span>
                LIVE INFERENCE RECORD · Analysis ID: <strong className="text-on-surface">{analysisResult.analysis_id}</strong> · Models: <span className="text-primary">{analysisResult.summary?.models_executed?.join(', ') || 'All Verified Models'}</span> · Total Detections: <strong className="text-on-surface">{analysisResult.summary?.total_detections ?? 0}</strong>
              </span>
            </div>
            <span className="text-[10px] text-[#50637c] hidden sm:inline">
              EXEC TIME: {analysisResult.summary?.execution_time_ms ? `${analysisResult.summary.execution_time_ms} ms` : 'COMPLETED'}
            </span>
          </div>
        ) : (
          <div className="flex items-center justify-between p-2.5 bg-[#0b111e] border border-[#1a2638] rounded-sm text-xs font-mono text-[#8ea4bf]">
            <div className="flex items-center space-x-2">
              <Info className="w-3.5 h-3.5 text-primary shrink-0" />
              <span>Acoustic anomaly inspection workspace. Upload a survey file to trigger live multi-model inference.</span>
            </div>
            <span className="text-[10px] text-[#50637c] hidden sm:inline">SWATH COVERAGE: 150m</span>
          </div>
        )}

        {/* ======================================================== */}
        {/* 2. DETECTION SUMMARY STRIP                               */}
        {/* ======================================================== */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
          <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3 flex items-center justify-between">
            <span className="text-[#8ea4bf] text-[10px] uppercase">TOTAL DETECTIONS</span>
            <span className="text-on-surface font-bold text-sm">{totalDetections}</span>
          </div>

          <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3 flex items-center justify-between">
            <span className="text-[#8ea4bf] text-[10px] uppercase">HIGH CONFIDENCE</span>
            <span className="text-primary font-bold text-sm">{highConfidenceCount}</span>
          </div>

          <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3 flex items-center justify-between">
            <span className="text-[#8ea4bf] text-[10px] uppercase">REQUIRES REVIEW</span>
            <span className="text-amber-400 font-bold text-sm">{reviewRequiredCount}</span>
          </div>

          <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3 flex items-center justify-between">
            <span className="text-[#8ea4bf] text-[10px] uppercase">FILTERED CLUTTER</span>
            <span className="text-[#64748b] font-bold text-sm">{filteredCount}</span>
          </div>
        </div>

        {/* ======================================================== */}
        {/* 3. MAIN WORKSPACE: CENTRAL SONAR + RESULT LIST           */}
        {/* ======================================================== */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* LEFT/CENTER: Central Sonar Swath View (8/12) */}
          <div className="lg:col-span-8 space-y-2">
            <div className="flex items-center justify-between px-3 py-2 bg-[#0b111e] border border-[#1a2638] rounded-t-sm text-xs font-mono">
              <div className="flex items-center space-x-2.5">
                <span className="w-1.5 h-1.5 rounded-sm bg-primary"></span>
                <span className="text-on-surface font-semibold text-[11px] uppercase tracking-wider">
                  ACOUSTIC SWATH · IMAGE-SPACE ANNOTATIONS
                </span>
                <span className="text-[#33465e]">|</span>
                <span className="text-[#64748b] text-[10px]">
                  {surveyFile ? surveyFile.name : (analysisResult?.image?.filename || 'RAW SIDE-SCAN SWATH')}
                </span>
              </div>

              <div className="flex items-center space-x-2">
                <span className="text-primary text-[10px]">
                  {detections.length} CANDIDATES
                </span>
              </div>
            </div>

            {/* Operator Sensitivity & Detector Control Toolbar */}
            <div className="px-3 py-2 bg-[#080d16] border-x border-b border-[#162234] font-mono text-xs flex flex-wrap items-center justify-between gap-2.5">
              <div className="flex items-center space-x-2.5">
                <div className="flex items-center space-x-1.5 text-[#8ea4bf] text-[10px]">
                  <Sliders className="w-3 h-3 text-primary" />
                  <span className="text-[#50637c]">CONFIDENCE CUTOFF:</span>
                  <span className="text-primary font-bold">{confidenceCutoff}%</span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="90"
                  step="5"
                  value={confidenceCutoff}
                  onChange={(e) => setConfidenceCutoff(Number(e.target.value))}
                  className="w-24 sm:w-32 h-1 bg-[#162234] rounded appearance-none cursor-pointer accent-teal-400"
                  title={`Detection threshold cutoff: ${confidenceCutoff}%`}
                />
              </div>

              {/* Target Model Filter Pills */}
              <div className="flex items-center space-x-1 text-[10px]">
                <span className="text-[#50637c] mr-0.5 hidden xl:inline">DETECTOR:</span>
                {[
                  { id: 'all', label: 'ALL' },
                  { id: 'subpipes', label: 'PIPELINE' },
                  { id: 'mines', label: 'MINES' },
                  { id: 'shipwreck', label: 'SHIPWRECK' },
                  { id: 'cylinder', label: 'CYLINDER' },
                  { id: 'ghostvision', label: 'GEAR' }
                ].map((m) => (
                  <button
                    key={m.id}
                    onClick={() => {
                      soundFx.playSonarPing(1200, 0.2);
                      setTargetModel(m.id);
                    }}
                    className={`px-1.5 py-0.5 rounded-xs transition-colors cursor-pointer border text-[9px] ${
                      targetModel === m.id
                        ? 'bg-primary/20 text-primary border-primary/50 font-bold'
                        : 'bg-[#0b111e] text-[#8ea4bf] border-[#162234] hover:text-white'
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              {/* Re-Scan Action Button */}
              {onRunAnalysis && surveyFile && (
                <button
                  onClick={() => handleTriggerReanalysis()}
                  disabled={isAnalyzing}
                  className="px-2.5 py-1 bg-primary/20 hover:bg-primary/30 border border-primary/40 text-primary text-[10px] font-bold rounded-xs flex items-center space-x-1 cursor-pointer transition-colors shrink-0 disabled:opacity-50"
                  title="Execute detection inference with selected threshold"
                >
                  <RefreshCw className={`w-3 h-3 ${isAnalyzing ? 'animate-spin' : ''}`} />
                  <span>{isAnalyzing ? 'SCANNING...' : 'RE-SCAN'}</span>
                </button>
              )}
            </div>

            {/* Sonar Viewport with Clean Scientific Bounding Boxes */}
            <div className="relative h-[340px] sm:h-[420px] lg:h-[460px] bg-[#02050c] border-x border-b border-[#1a2638] rounded-b-sm overflow-hidden select-none">
              <div 
                className="absolute inset-0 opacity-60 pointer-events-none"
                style={{
                  backgroundImage: 'linear-gradient(to bottom, #02050c 0%, #071220 50%, #02050c 100%), repeating-radial-gradient(circle at 50% 50%, transparent 0, transparent 3px, rgba(45, 212, 191, 0.05) 4px, transparent 5px)',
                  backgroundSize: '100% 100%, 20px 20px'
                }}
              />

              {imageUrl && (
                <img 
                  src={imageUrl} 
                  alt="Side-Scan Sonar Swath" 
                  className="absolute inset-0 w-full h-full object-cover opacity-85 contrast-125"
                  onError={(e) => {
                    if (surveyFile && (surveyFile instanceof File || surveyFile instanceof Blob)) {
                      e.target.src = URL.createObjectURL(surveyFile);
                    } else {
                      e.target.style.display = 'none';
                    }
                  }}
                />
              )}

              {/* Inference Scanning Overlay */}
              {isAnalyzing && (
                <div className="absolute inset-0 bg-[#060911]/80 backdrop-blur-xs flex flex-col items-center justify-center space-y-3 z-30 font-mono text-xs">
                  <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
                  <span className="text-primary tracking-wider uppercase font-semibold">
                    Running Multi-Model Inference...
                  </span>
                  <span className="text-[#8ea4bf] text-[11px] font-sans">
                    Evaluating acoustic backscatter & resolving semantic classes
                  </span>
                </div>
              )}

              {/* Nadir Water Column Line */}
              <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-4 bg-[#010408] border-x border-[#1a2638] flex flex-col justify-between items-center py-2.5 font-mono text-[8px] text-[#50637c] pointer-events-none z-10">
                <span>NADIR</span>
                <span className="text-primary font-bold">0m</span>
                <span>NADIR</span>
              </div>

              {/* Range Scale */}
              <div className="absolute top-2 inset-x-4 flex justify-between font-mono text-[9px] text-[#50637c] pointer-events-none z-10">
                <span>PORT (-75m)</span>
                <span>STARBOARD (+75m)</span>
              </div>

              {/* Clean Scientific Bounding Boxes */}
              {!isAnalyzing && detections.map((det) => {
                const isSelected = det.id === selectedId;
                const isHovered = det.id === hoveredId;
                const box = det.box || det.bbox || { x: 0, y: 0, w: 0, h: 0 };

                return (
                  <div
                    key={det.id}
                    onClick={() => handleSelectDetection(det)}
                    onMouseEnter={() => setHoveredId(det.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    style={{
                      left: `${box.x}%`,
                      top: `${box.y}%`,
                      width: `${box.w}%`,
                      height: `${box.h}%`
                    }}
                    className={`absolute cursor-pointer transition-colors z-20 ${
                      isSelected
                        ? 'border border-primary bg-primary/10'
                        : isHovered
                          ? 'border border-[#2dd4bf]/80 bg-[#2dd4bf]/5'
                          : 'border border-[#2dd4bf]/40 hover:border-primary bg-transparent'
                    }`}
                  >
                    {/* Corner Reticle Marks */}
                    <div className="absolute -top-0.5 -left-0.5 w-1.5 h-1.5 border-t border-l border-primary pointer-events-none"></div>
                    <div className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 border-t border-r border-primary pointer-events-none"></div>
                    <div className="absolute -bottom-0.5 -left-0.5 w-1.5 h-1.5 border-b border-l border-primary pointer-events-none"></div>
                    <div className="absolute -bottom-0.5 -right-0.5 w-1.5 h-1.5 border-b border-r border-primary pointer-events-none"></div>

                    {/* Scientific Identification Tag */}
                    <div className="absolute -top-5 left-0 flex items-center space-x-1 font-mono text-[9px] bg-[#060911]/95 px-1.5 py-0.2 rounded-sm border border-[#1a2638] text-on-surface whitespace-nowrap shadow-sm">
                      <span className="font-bold text-primary">{det.code}</span>
                      <span className="text-[#8ea4bf]">{det.className}</span>
                      <span className="text-[#33465e]">|</span>
                      <span className="text-[#f1f5f9]">{det.confidence}%</span>
                    </div>

                    {det.shadowLength && (
                      <div className="absolute right-0 bottom-0 text-[8px] font-mono text-[#50637c] bg-[#02050c]/90 px-1 pointer-events-none">
                        SHADOW: {det.shadowLength}
                      </div>
                    )}
                  </div>
                );
              })}

              <div className="absolute bottom-2 inset-x-6 flex justify-between font-mono text-[9px] text-[#50637c] pointer-events-none z-10 bg-gradient-to-t from-[#02050c]/95 to-transparent pt-3">
                <span>-75m</span>
                <span>-50m</span>
                <span>-25m</span>
                <span className="text-primary font-bold">0m</span>
                <span>+25m</span>
                <span>+50m</span>
                <span>+75m</span>
              </div>
            </div>
          </div>

          {/* RIGHT: Candidate Result Panel (4/12) */}
          <div className="lg:col-span-4 space-y-4 flex flex-col justify-between">
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-[#162234]">
                <span className="font-mono text-xs tracking-wider text-on-surface font-semibold uppercase">
                  Candidate Targets
                </span>
                <span className="font-mono text-[10px] text-[#64748b]">
                  {detections.length} REGISTERED
                </span>
              </div>

              {/* Detection Items List */}
              <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                {isAnalyzing ? (
                  <div className="py-12 text-center space-y-2 font-mono text-xs">
                    <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin mx-auto"></div>
                    <p className="text-primary font-semibold uppercase">Inference Running...</p>
                    <p className="text-[#64748b] text-[11px] font-sans">Scanning survey swath</p>
                  </div>
                ) : analysisError ? (
                  <div className="py-10 px-3 text-center space-y-2 font-mono text-xs">
                    <AlertTriangle className="w-5 h-5 text-red-400 mx-auto" />
                    <p className="text-red-300 font-semibold uppercase">Inference Aborted</p>
                    <p className="font-sans text-[11px] text-[#94a3b8] leading-relaxed">
                      {analysisError}
                    </p>
                  </div>
                ) : detections.length === 0 ? (
                  <div className="py-10 px-3 text-center space-y-2 font-mono text-xs">
                    <CheckCircle2 className="w-5 h-5 text-primary mx-auto opacity-75" />
                    <p className="text-on-surface font-semibold uppercase">No Objects Detected</p>
                    <p className="font-sans text-[11px] text-[#8ea4bf] leading-relaxed">
                      No objects met the {confidenceCutoff}% confidence cutoff in this swath.
                    </p>
                    {onRunAnalysis && surveyFile && (
                      <button
                        onClick={() => handleTriggerReanalysis(15)}
                        disabled={isAnalyzing}
                        className="mt-2 px-3 py-1.5 bg-[#101b2c] hover:bg-primary/20 border border-[#22354e] hover:border-primary text-primary text-[10px] rounded-xs font-semibold cursor-pointer transition-colors inline-flex items-center space-x-1.5"
                      >
                        <RefreshCw className="w-3 h-3" />
                        <span>Lower Cutoff to 15% & Re-Scan</span>
                      </button>
                    )}
                  </div>
                ) : (
                  detections.map((det) => {
                    const isSelected = det.id === selectedId;

                    return (
                      <div
                        key={det.id}
                        onClick={() => handleSelectDetection(det)}
                        className={`p-2.5 rounded-sm border font-mono text-xs cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-[#101b2c] border-[#22354e] text-on-surface'
                            : 'bg-[#080d16] hover:bg-[#0e1625] border-[#162234] text-[#8ea4bf]'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center space-x-2 truncate">
                            <span className="text-primary font-bold text-[10px]">{det.code}</span>
                            <span className="font-bold text-on-surface text-[11px] truncate">{det.className}</span>
                          </div>

                          <div className="flex items-center space-x-1.5 shrink-0">
                            <span className={`px-1.5 py-0.2 rounded-xs text-[9px] font-bold border ${
                              det.priority === 'HIGH' ? 'bg-red-950/40 text-red-300 border-red-500/30' :
                              det.priority === 'MEDIUM' ? 'bg-amber-950/40 text-amber-300 border-amber-500/30' :
                              'bg-slate-800/40 text-slate-300 border-slate-600/30'
                            }`} title={det.priority_reason || ''}>
                              {det.priority || 'LOW'}
                            </span>
                            <button
                              onClick={(e) => handleToggleStatus(det.id, e)}
                              title="Toggle review state"
                              className={`px-1.5 py-0.2 rounded-sm text-[9px] font-semibold tracking-wider cursor-pointer border ${
                                det.status === 'VERIFIED'
                                  ? 'bg-[#102a24] text-[#99f6e4] border-[#1b5e50]'
                                  : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                              }`}
                            >
                              {det.status}
                            </button>
                          </div>
                        </div>

                        <div className="flex justify-between items-center text-[10px] text-[#64748b] mt-1">
                          <span>Confidence · Model</span>
                          <span className="text-on-surface font-semibold">
                            {det.confidence}% · <span className="text-[#8ea4bf]">{det.model || 'model'}</span>
                          </span>
                        </div>

                        {det.priority_reason && (
                          <div className="text-[10px] text-[#8ea4bf] italic mt-0.5">
                            {det.priority_reason}
                          </div>
                        )}

                        {det.acousticFeature && (
                          <p className="font-sans text-[11px] text-[#64748b] font-normal mt-1 line-clamp-1">
                            {det.acousticFeature}
                          </p>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* False-Positive Filtering Notice */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-1 font-mono text-xs">
              <div className="flex items-center justify-between text-on-surface font-semibold uppercase">
                <div className="flex items-center space-x-1.5">
                  <Filter className="w-3.5 h-3.5 text-primary" />
                  <span>Clutter Suppression</span>
                </div>
                <span className="text-[10px] text-primary">MULTI-MODEL RESOLUTION</span>
              </div>
              <p className="font-sans text-[11px] text-[#64748b] leading-relaxed">
                Candidate regions are screened to suppress false alarms caused by acoustic shadows and natural seafloor texture.
              </p>
            </div>

            {/* Next Action Box */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-2.5">
              <div className="flex items-center justify-between font-mono text-[10px] text-[#64748b] uppercase">
                <span>Next Workflow Phase</span>
                <span className="text-primary font-medium">04 — Geolocation & Evidence</span>
              </div>

              <button
                id="btn-continue-geolocation"
                onClick={handleContinueToGeolocation}
                className="w-full inline-flex items-center justify-center space-x-2.5 px-5 py-3 rounded-sm bg-[#132338] hover:bg-[#1a2f4a] border border-[#273d5c] hover:border-primary/60 text-[#f1f5f9] font-mono text-xs uppercase tracking-wider font-semibold transition-colors cursor-pointer"
              >
                <span>Continue to Geolocation</span>
                <ArrowRight className="w-3.5 h-3.5 text-primary" />
              </button>

              <p className="font-sans text-[11px] text-center text-[#64748b]">
                Review detection evidence and assess geographic localization.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

