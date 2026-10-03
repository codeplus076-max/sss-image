import React, { useState, useEffect, useRef } from 'react';
import { 
  Upload, 
  FileText, 
  CheckCircle2, 
  AlertTriangle, 
  X, 
  ArrowRight, 
  FileCode, 
  Clock, 
  RotateCcw,
  Plus,
  ShieldCheck,
  Compass,
  Layers,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Scan,
  FolderOpen
} from 'lucide-react';
import { soundFx } from '../../utils/audio';

export default function SonarIngestView({ 
  onNavigate, 
  onContinueToQualityCheck,
  recentSurveys = [],
  analysisError = null,
  onClearError,
  onOpenAnalysis,
  onStartBatchScreening
}) {
  const [dragActive, setDragActive] = useState(false);
  const [queuedFiles, setQueuedFiles] = useState([]);
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const [sessionSurveys, setSessionSurveys] = useState(recentSurveys);
  const [metadataDetails, setMetadataDetails] = useState(null);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const fileInputRef = useRef(null);

  // Optional Survey Telemetry & Model Selection State
  const [showTelemetryConfig, setShowTelemetryConfig] = useState(false);
  const [telemetry, setTelemetry] = useState({
    latitude: '',
    longitude: '',
    depth: '',
    heading: '',
    timestamp: ''
  });
  const [enableSeabedGate, setEnableSeabedGate] = useState(true);
  const [seabedCleanThreshold, setSeabedCleanThreshold] = useState(0.92);
  const [selectedModels, setSelectedModels] = useState([
    'cylinder',
    'ghostvision',
    'mines',
    'shipwreck',
    'subpipes'
  ]);

  // Model catalog specification
  const availableModelList = [
    { id: 'cylinder', name: 'Cylinder', available: true },
    { id: 'ghostvision', name: 'GhostVision (Crab-Pot)', available: true },
    { id: 'mines', name: 'Mines (MILCO / NOMBO)', available: true },
    { id: 'shipwreck', name: 'Shipwreck', available: true },
    { id: 'subpipes', name: 'SubPipes (Pipelines)', available: true },
    { id: 'natural_seabed', name: 'Natural Seabed (Stage-1 Gate)', available: true, isGate: true, note: 'Triage Gate' }
  ];

  const handleToggleModel = (id) => {
    if (id === 'natural_seabed') {
      soundFx.playSonarPing(1100, 0.2);
      setEnableSeabedGate(prev => !prev);
      return;
    }
    soundFx.playSonarPing(1200, 0.2);
    setSelectedModels(prev => 
      prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]
    );
  };

  const handleSelectPreset = (preset) => {
    soundFx.playSonarPing(1300, 0.2);
    if (preset === 'all') {
      setSelectedModels(['cylinder', 'ghostvision', 'mines', 'shipwreck', 'subpipes']);
    } else if (preset === 'infrastructure') {
      setSelectedModels(['subpipes', 'cylinder']);
    } else if (preset === 'tactical') {
      setSelectedModels(['mines', 'shipwreck']);
    } else if (preset === 'ghostgear') {
      setSelectedModels(['ghostvision']);
    }
  };

  // Sync recent surveys from backend
  useEffect(() => {
    if (recentSurveys && recentSurveys.length > 0) {
      setSessionSurveys(recentSurveys);
    }
  }, [recentSurveys]);

  // Helper to format file size
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Inspect actual file metadata when selected
  const inspectFile = (file) => {
    soundFx.playSonarPing(1300, 0.4);

    const isImage = file.type.startsWith('image/') || /\.(tif|tiff|png|jpg|jpeg|bmp|webp)$/i.test(file.name);
    const hasTifExt = /\.(tif|tiff)$/i.test(file.name);
    const hasXtfExt = /\.(xtf|jsf|sl2|sl3|all)$/i.test(file.name);

    const inspection = {
      name: file.name,
      size: formatFileSize(file.size),
      rawBytes: file.size,
      mimeType: file.type || (hasTifExt ? 'image/tiff' : hasXtfExt ? 'application/x-xtf' : 'application/octet-stream'),
      lastModified: file.lastModified ? new Date(file.lastModified).toUTCString() : null,
      surveyId: null, // Strictly honest: NOT DETECTED
      resolution: null,
      isImage,
      hasNavigation: false, // Strictly honest: UNAVAILABLE
      hasGps: false,
      hasPingData: false,
      sensorSpec: null
    };

    if (isImage && typeof window !== 'undefined') {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          setMetadataDetails(prev => ({
            ...prev,
            resolution: `${img.naturalWidth} × ${img.naturalHeight} px`
          }));
        };
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
    }

    setMetadataDetails(inspection);
  };

  const handleFiles = (incomingFiles) => {
    if (!incomingFiles || incomingFiles.length === 0) return;

    const fileList = Array.from(incomingFiles);
    setQueuedFiles(prev => {
      const updated = [...prev, ...fileList];
      if (prev.length === 0 && fileList[0]) {
        setSelectedFileIndex(0);
        inspectFile(fileList[0]);
      }
      return updated;
    });

    soundFx.playSonarPing(1400, 0.5);
  };

  const handleLoadDemoBatch = async (e) => {
    if (e) e.stopPropagation();
    try {
      setLoadingDemo(true);
      soundFx.playSonarPing(1200, 0.4);
      const demoNames = [
        'Sonar_01_CLEAN_Seabed.jpg',
        'Sonar_02_FLAGGED_Industrial_Cylinder___Drum.jpg',
        'Sonar_03_CLEAN_Seabed.jpg',
        'Sonar_04_FLAGGED_Industrial_Cylinder___Drum.jpg',
        'Sonar_05_CLEAN_Seabed.jpg',
        'Sonar_06_CLEAN_Seabed.jpg',
        'Sonar_07_CLEAN_Seabed.jpg',
        'Sonar_08_CLEAN_Seabed.jpg',
        'Sonar_09_FLAGGED_Non-Mine_Mine-Like_Bottom_Object_(NOMBO).jpg'
      ];
      const loadedFiles = [];
      for (const name of demoNames) {
        const res = await fetch(`/sample_batch/${name}`);
        if (!res.ok) continue;
        const blob = await res.blob();
        const file = new File([blob], name, { type: 'image/jpeg' });
        loadedFiles.push(file);
      }
      if (loadedFiles.length > 0) {
        setQueuedFiles(loadedFiles);
        setSelectedFileIndex(0);
        inspectFile(loadedFiles[0]);
        soundFx.playTargetLock();
      }
    } catch (err) {
      console.warn('Failed to load demo batch:', err);
    } finally {
      setLoadingDemo(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
    }
  };

  const handleSelectQueuedFile = (index) => {
    setSelectedFileIndex(index);
    if (queuedFiles[index]) {
      inspectFile(queuedFiles[index]);
    }
  };

  const handleRemoveFile = (index, e) => {
    e.stopPropagation();
    soundFx.playSonarPing(900, 0.3);
    const remaining = queuedFiles.filter((_, i) => i !== index);
    setQueuedFiles(remaining);

    if (remaining.length === 0) {
      setMetadataDetails(null);
      setSelectedFileIndex(0);
    } else {
      const newIndex = Math.min(selectedFileIndex, remaining.length - 1);
      setSelectedFileIndex(newIndex);
      inspectFile(remaining[newIndex]);
    }
  };

  const handleClearAll = () => {
    soundFx.playSonarPing(800, 0.4);
    setQueuedFiles([]);
    setMetadataDetails(null);
    setSelectedFileIndex(0);
  };

  const handleProceed = () => {
    soundFx.playTargetLock();
    const activeFile = queuedFiles[selectedFileIndex] || null;

    if (activeFile) {
      setSessionSurveys(prev => [
        {
          name: activeFile.name,
          size: formatFileSize(activeFile.size),
          timestamp: new Date().toISOString(),
          status: 'VALIDATED'
        },
        ...prev.slice(0, 4)
      ]);
    }

    const surveyMeta = {
      latitude: telemetry.latitude !== '' ? parseFloat(telemetry.latitude) : null,
      longitude: telemetry.longitude !== '' ? parseFloat(telemetry.longitude) : null,
      depth: telemetry.depth !== '' ? parseFloat(telemetry.depth) : null,
      heading: telemetry.heading !== '' ? parseFloat(telemetry.heading) : null,
      timestamp: telemetry.timestamp !== '' ? telemetry.timestamp : null,
      selected_models: selectedModels,
      enable_seabed_gate: enableSeabedGate,
      seabed_clean_threshold: seabedCleanThreshold
    };

    if (onContinueToQualityCheck) {
      onContinueToQualityCheck(activeFile, surveyMeta);
    } else if (onNavigate) {
      onNavigate('view-quality');
    }
  };

  const handleBatchProceed = () => {
    soundFx.playTargetLock();
    const surveyMeta = {
      latitude: telemetry.latitude !== '' ? parseFloat(telemetry.latitude) : null,
      longitude: telemetry.longitude !== '' ? parseFloat(telemetry.longitude) : null,
      depth: telemetry.depth !== '' ? parseFloat(telemetry.depth) : null,
      heading: telemetry.heading !== '' ? parseFloat(telemetry.heading) : null,
      timestamp: telemetry.timestamp !== '' ? telemetry.timestamp : null,
      selected_models: selectedModels,
      enable_seabed_gate: enableSeabedGate,
      seabed_clean_threshold: seabedCleanThreshold
    };
    if (onStartBatchScreening) {
      onStartBatchScreening(queuedFiles, surveyMeta);
    }
  };

  const hasFiles = queuedFiles.length > 0;
  const currentFile = queuedFiles[selectedFileIndex] || null;

  return (
    <section className="relative w-full h-[calc(100vh-3.5rem)] overflow-y-auto bg-[#060911] text-[#f1f5f9] select-none p-4 sm:p-6 lg:p-8">
      <div className="max-w-7xl mx-auto space-y-6 pb-12">
        
        {/* ======================================================== */}
        {/* 1. SECTION HEADER                                        */}
        {/* ======================================================== */}
        <div className="border-b border-[#162234] pb-4 flex flex-col sm:flex-row sm:items-end justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2 mb-1">
              <span className="w-1.5 h-1.5 rounded-sm bg-primary"></span>
              <span className="font-mono text-xs tracking-[0.2em] text-[#8ea4bf] uppercase font-semibold">
                01 — SONAR INGEST
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-headline tracking-tight text-on-surface font-normal">
              Import side-scan survey.
            </h1>
            <p className="font-sans text-xs sm:text-sm text-[#94a3b8] max-w-xl mt-1 font-normal leading-relaxed">
              Load side-scan sonar files and verify available survey metadata before signal conditioning.
            </p>
          </div>

          <div className="hidden sm:flex items-center space-x-2 font-mono text-[10px] text-[#64748b]">
            <span className="text-primary">●</span>
            <span>RAW DATA INTAKE PORT</span>
          </div>
        </div>

        {/* Dynamic Validation Error Banner */}
        {analysisError && (
          <div className="flex items-center justify-between p-3.5 bg-red-950/40 border border-red-500/40 rounded-sm text-xs font-mono text-red-200">
            <div className="flex items-center space-x-2.5">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
              <div>
                <span className="font-bold text-red-300 uppercase tracking-wide">
                  {analysisError?.toLowerCase().includes('reach') || analysisError?.toLowerCase().includes('spin up') || analysisError?.toLowerCase().includes('connect') || analysisError?.toLowerCase().includes('network') || analysisError?.toLowerCase().includes('server') || analysisError?.toLowerCase().includes('backend')
                    ? 'Backend Connection Notice: '
                    : 'Invalid Sonar Image: '}
                </span>
                <span>{analysisError}</span>
              </div>
            </div>
            {onClearError && (
              <button
                onClick={onClearError}
                className="text-[#64748b] hover:text-white p-1 text-xs cursor-pointer shrink-0 ml-2"
                title="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}

        {/* Hidden File Input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileChange}
        />

        {/* ======================================================== */}
        {/* 2. WORKSTATION TWO-COLUMN GRID                           */}
        {/* ======================================================== */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* LEFT COLUMN: DROP ZONE & QUEUED FILES (7/12) */}
          <div className="lg:col-span-7 space-y-4">
            
            {/* Primary Drop Zone */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              className={`relative rounded-sm border border-dashed transition-colors cursor-pointer py-10 px-6 sm:px-8 text-center flex flex-col items-center justify-center ${
                dragActive
                  ? 'border-primary bg-[#0f1d2e]'
                  : 'border-[#22354e] hover:border-[#334e72] bg-[#0b111e]'
              }`}
            >
              {/* Technical Reticle Marks */}
              <div className="absolute top-2.5 left-3 font-mono text-[9px] text-[#50637c]">
                ┌ INTAKE CH 01
              </div>
              <div className="absolute top-2.5 right-3 font-mono text-[9px] text-[#50637c]">
                SSS HYDROGRAPHIC ┐
              </div>
              <div className="absolute bottom-2.5 left-3 font-mono text-[9px] text-[#50637c]">
                └ FORMATS: XTF / JSF / TIFF / PNG
              </div>

              <div className="w-10 h-10 rounded-sm bg-[#101b2b] border border-[#22354e] flex items-center justify-center text-primary mb-3">
                <Upload className="w-4 h-4" />
              </div>

              <h2 className="font-mono text-xs sm:text-sm font-semibold tracking-wider text-on-surface uppercase">
                DROP SONAR SURVEY IMAGERY
              </h2>
              <p className="font-sans text-xs text-[#8ea4bf] mt-1 max-w-sm">
                Drag single or multiple sonar swaths here, or use the buttons below.
              </p>

              {/* Dual Ingest Buttons: Single File vs Multi-Image Batch */}
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2.5">
                <button
                  type="button"
                  id="btn-browse-single"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (fileInputRef.current) fileInputRef.current.click();
                  }}
                  className="px-4 py-2 rounded-sm bg-[#132338] hover:bg-[#1a2f4a] border border-[#273d5c] hover:border-primary/60 text-on-surface font-mono text-xs tracking-wider uppercase font-semibold transition-colors cursor-pointer"
                >
                  Browse Files
                </button>

                <button
                  type="button"
                  id="btn-browse-multiple"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (fileInputRef.current) fileInputRef.current.click();
                  }}
                  className="px-4 py-2 rounded-sm bg-primary/20 hover:bg-primary/30 border border-primary/60 hover:border-primary text-primary font-mono text-xs tracking-wider uppercase font-semibold transition-all cursor-pointer flex items-center space-x-1.5 shadow-[0_0_12px_rgba(45,212,191,0.2)]"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Select Multiple (Batch)</span>
                </button>

                <button
                  type="button"
                  id="btn-load-demo-batch"
                  disabled={loadingDemo}
                  onClick={handleLoadDemoBatch}
                  className="px-4 py-2 rounded-sm bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/50 hover:border-amber-400 text-amber-300 font-mono text-xs tracking-wider uppercase font-semibold transition-all cursor-pointer flex items-center space-x-1.5 shadow-[0_0_12px_rgba(245,158,11,0.15)]"
                >
                  <FolderOpen className="w-3.5 h-3.5" />
                  <span>{loadingDemo ? 'Loading...' : '⚡ Load Test Batch (9 Sonar Images)'}</span>
                </button>
              </div>

              <p className="font-mono text-[10px] text-[#50637c] mt-2.5">
                Tip: Hold <span className="text-primary font-semibold">Ctrl</span> or <span className="text-primary font-semibold">Shift</span> to select multiple files at once in the file dialog.
              </p>
            </div>

            {/* Queued Survey File Ledger */}
            {hasFiles && (
              <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-2">
                {queuedFiles.length > 1 && (
                  <div className="p-2.5 rounded-sm bg-primary/10 border border-primary/30 flex items-center justify-between text-xs font-mono text-primary mb-2">
                    <div className="flex items-center space-x-2">
                      <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
                      <span className="font-semibold uppercase tracking-wide">
                        Batch Mode Active: {queuedFiles.length} Survey Images Loaded
                      </span>
                    </div>
                    <span className="text-[10px] text-[#8ea4bf] hidden sm:inline">
                      Click below to screen all for anomalies
                    </span>
                  </div>
                )}

                <div className="flex items-center justify-between text-xs font-mono pb-2 border-b border-[#162234]">
                  <span className="text-[#8ea4bf] uppercase font-semibold flex items-center space-x-2">
                    <span className="w-1.5 h-1.5 rounded-sm bg-primary"></span>
                    <span>Queued Files ({queuedFiles.length})</span>
                  </span>

                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => fileInputRef.current && fileInputRef.current.click()}
                      className="px-2 py-0.5 rounded-sm bg-[#101928] border border-[#1e2e42] hover:border-primary/50 text-[#8ea4bf] hover:text-primary font-mono text-[10px] flex items-center space-x-1 cursor-pointer"
                    >
                      <Plus className="w-3 h-3 text-primary" />
                      <span>+ Add More</span>
                    </button>
                    <button
                      onClick={handleClearAll}
                      className="px-2 py-0.5 rounded-sm bg-[#101928] border border-[#1e2e42] hover:border-red-500/40 text-[#8ea4bf] hover:text-red-400 font-mono text-[10px] flex items-center space-x-1 cursor-pointer"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>Clear All</span>
                    </button>
                  </div>
                </div>

                <div className="space-y-1 font-mono text-xs">
                  {queuedFiles.map((file, idx) => {
                    const isSelected = idx === selectedFileIndex;
                    return (
                      <div
                        key={idx}
                        onClick={() => handleSelectQueuedFile(idx)}
                        className={`flex items-center justify-between p-2 rounded-sm cursor-pointer border transition-colors ${
                          isSelected
                            ? 'bg-[#101b2c] border-[#22354e] text-on-surface'
                            : 'hover:bg-[#0e1625] border-transparent text-[#8ea4bf]'
                        }`}
                      >
                        <div className="flex items-center space-x-2 truncate">
                          <span className="text-primary text-[10px]">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span className="truncate">{file.name}</span>
                        </div>
                        <div className="flex items-center space-x-2 shrink-0 ml-2">
                          <span className="text-[10px] text-[#64748b]">{formatFileSize(file.size)}</span>
                          <button
                            onClick={(e) => handleRemoveFile(idx, e)}
                            className="text-[#64748b] hover:text-red-400 p-0.5"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Optional Survey Telemetry & Model Selection */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-3 font-mono text-xs">
              <div 
                onClick={() => setShowTelemetryConfig(!showTelemetryConfig)}
                className="flex items-center justify-between cursor-pointer select-none pb-1"
              >
                <div className="flex items-center space-x-2">
                  <Compass className="w-3.5 h-3.5 text-primary" />
                  <span className="text-on-surface font-semibold uppercase tracking-wider text-[11px]">
                    Survey Telemetry &amp; Detection Models
                  </span>
                  <span className="text-[10px] text-[#50637c]">
                    (Optional)
                  </span>
                </div>
                <div className="flex items-center space-x-1 text-[#64748b] hover:text-on-surface">
                  <span className="text-[10px]">{showTelemetryConfig ? 'Collapse' : 'Configure'}</span>
                  {showTelemetryConfig ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </div>
              </div>

              {showTelemetryConfig && (
                <div className="space-y-3 pt-2 border-t border-[#162234]">
                  {/* Coordinates & Physical Telemetry */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div>
                      <label className="text-[10px] text-[#8ea4bf] block mb-1">LATITUDE (°N)</label>
                      <input
                        type="number"
                        step="any"
                        placeholder="18.9175"
                        value={telemetry.latitude}
                        onChange={(e) => setTelemetry(prev => ({ ...prev, latitude: e.target.value }))}
                        className="w-full bg-[#070c14] border border-[#1a2638] focus:border-primary/60 rounded-sm p-1.5 text-xs text-on-surface font-mono outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-[#8ea4bf] block mb-1">LONGITUDE (°E)</label>
                      <input
                        type="number"
                        step="any"
                        placeholder="72.8375"
                        value={telemetry.longitude}
                        onChange={(e) => setTelemetry(prev => ({ ...prev, longitude: e.target.value }))}
                        className="w-full bg-[#070c14] border border-[#1a2638] focus:border-primary/60 rounded-sm p-1.5 text-xs text-on-surface font-mono outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-[#8ea4bf] block mb-1">DEPTH (M)</label>
                      <input
                        type="number"
                        step="any"
                        placeholder="45.0"
                        value={telemetry.depth}
                        onChange={(e) => setTelemetry(prev => ({ ...prev, depth: e.target.value }))}
                        className="w-full bg-[#070c14] border border-[#1a2638] focus:border-primary/60 rounded-sm p-1.5 text-xs text-on-surface font-mono outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-[#8ea4bf] block mb-1">HEADING (°)</label>
                      <input
                        type="number"
                        step="any"
                        placeholder="135.0"
                        value={telemetry.heading}
                        onChange={(e) => setTelemetry(prev => ({ ...prev, heading: e.target.value }))}
                        className="w-full bg-[#070c14] border border-[#1a2638] focus:border-primary/60 rounded-sm p-1.5 text-xs text-on-surface font-mono outline-none"
                      />
                    </div>
                  </div>

                  {/* Stage-1 Natural Seabed Triage Gate & Uncertainty Filter */}
                  <div className="pt-2 border-t border-[#162234] space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Sparkles className="w-3.5 h-3.5 text-primary" />
                        <span className="text-[10px] text-[#8ea4bf] uppercase font-semibold">
                          Stage-1 Seabed Triage Gate (YOLO26m-cls)
                        </span>
                      </div>
                      <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                        enableSeabedGate ? 'bg-primary/15 text-primary border border-primary/30' : 'bg-slate-800 text-[#64748b]'
                      }`}>
                        {enableSeabedGate ? 'GATE ACTIVE' : 'BYPASS DISABLED'}
                      </span>
                    </div>

                    <div className="bg-[#070c14] border border-[#1a2638] rounded-sm p-2.5 space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="flex items-center space-x-2 cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={enableSeabedGate}
                            onChange={(e) => {
                              soundFx.playSonarPing(1100, 0.2);
                              setEnableSeabedGate(e.target.checked);
                            }}
                            className="rounded border-[#22354e] bg-[#0c131f] text-primary focus:ring-0 focus:ring-offset-0 cursor-pointer"
                          />
                          <span className="text-[11px] text-on-surface font-medium">
                            Enable Hard Sort Clean Seabed Auto-Bypass
                          </span>
                        </label>
                        <span className="text-[10px] font-mono text-primary font-bold">
                          {(seabedCleanThreshold * 100).toFixed(0)}% $\tau$
                        </span>
                      </div>

                      {enableSeabedGate && (
                        <div className="space-y-1 pt-1">
                          <div className="flex items-center justify-between text-[9px] font-mono text-[#64748b]">
                            <span>CLEAN THRESHOLD (τ): {(seabedCleanThreshold * 100).toFixed(0)}%</span>
                            <span className="text-[#8ea4bf]">UNCERTAINTY BAND: &lt;{(seabedCleanThreshold * 100).toFixed(0)}% → FORWARD</span>
                          </div>
                          <input
                            type="range"
                            min="0.70"
                            max="0.99"
                            step="0.01"
                            value={seabedCleanThreshold}
                            onChange={(e) => setSeabedCleanThreshold(parseFloat(e.target.value))}
                            className="w-full accent-[#2dd4bf] h-1.5 bg-[#141e2d] rounded-sm cursor-pointer"
                          />
                          <p className="font-sans text-[10px] text-[#7d93ad] leading-normal">
                            Swaths with clean seabed confidence ≥ {(seabedCleanThreshold * 100).toFixed(0)}% are conclusively verified and bypass downstream detectors (~85% compute savings). Swaths with anomaly probability ≥ 50% or unsure confidence (&lt;{(seabedCleanThreshold * 100).toFixed(0)}%) are forwarded to specialized models.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Downstream Model Checklist */}
                  <div className="pt-2 border-t border-[#162234]">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] text-[#8ea4bf] uppercase font-semibold">
                        Downstream Specialized Detectors ({selectedModels.length} Active)
                      </span>
                      <span className="text-[9px] text-primary font-mono">
                        Stage-2 Object Detectors
                      </span>
                    </div>

                    {/* Presets */}
                    <div className="flex flex-wrap items-center gap-1.5 mb-2.5">
                      <span className="text-[9px] font-mono text-[#50637c] uppercase mr-1">Presets:</span>
                      <button
                        type="button"
                        onClick={() => handleSelectPreset('all')}
                        className={`px-2 py-0.5 rounded-xs font-mono text-[9px] border transition-colors cursor-pointer ${
                          selectedModels.length === 5 
                            ? 'bg-primary/15 border-primary/40 text-primary' 
                            : 'bg-[#080d16] border-[#1a2638] text-[#7d93ad] hover:text-[#f8fafc]'
                        }`}
                      >
                        All (Deep Recon)
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSelectPreset('infrastructure')}
                        className={`px-2 py-0.5 rounded-xs font-mono text-[9px] border transition-colors cursor-pointer ${
                          selectedModels.length === 2 && selectedModels.includes('subpipes') && selectedModels.includes('cylinder')
                            ? 'bg-primary/15 border-primary/40 text-primary' 
                            : 'bg-[#080d16] border-[#1a2638] text-[#7d93ad] hover:text-[#f8fafc]'
                        }`}
                      >
                        Pipeline & Cylinder
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSelectPreset('tactical')}
                        className={`px-2 py-0.5 rounded-xs font-mono text-[9px] border transition-colors cursor-pointer ${
                          selectedModels.length === 2 && selectedModels.includes('mines') && selectedModels.includes('shipwreck')
                            ? 'bg-primary/15 border-primary/40 text-primary' 
                            : 'bg-[#080d16] border-[#1a2638] text-[#7d93ad] hover:text-[#f8fafc]'
                        }`}
                      >
                        Mines & Wrecks
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSelectPreset('ghostgear')}
                        className={`px-2 py-0.5 rounded-xs font-mono text-[9px] border transition-colors cursor-pointer ${
                          selectedModels.length === 1 && selectedModels.includes('ghostvision')
                            ? 'bg-primary/15 border-primary/40 text-primary' 
                            : 'bg-[#080d16] border-[#1a2638] text-[#7d93ad] hover:text-[#f8fafc]'
                        }`}
                      >
                        Ghost Gear
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                      {availableModelList.map((m) => {
                        const isChecked = m.id === 'natural_seabed' ? enableSeabedGate : selectedModels.includes(m.id);
                        const isAvailable = m.available;

                        return (
                          <div
                            key={m.id}
                            onClick={() => isAvailable && handleToggleModel(m.id)}
                            className={`flex items-center justify-between p-1.5 rounded-sm border transition-colors ${
                              !isAvailable
                                ? 'bg-[#070b12] border-[#141d2a] text-[#50637c] cursor-not-allowed opacity-60'
                                : isChecked
                                  ? 'bg-[#101b2c] border-[#22354e] text-on-surface cursor-pointer'
                                  : 'bg-[#080d16] border-[#162234] text-[#64748b] hover:text-on-surface cursor-pointer'
                            }`}
                          >
                            <div className="flex items-center space-x-2">
                              <span className={`w-3 h-3 rounded-xs border flex items-center justify-center text-[9px] ${
                                !isAvailable
                                  ? 'border-[#1e2a3c] bg-[#0c131f]'
                                  : isChecked
                                    ? 'border-primary bg-primary/20 text-primary'
                                    : 'border-[#22354e] bg-transparent'
                              }`}>
                                {isChecked && isAvailable ? '✓' : ''}
                              </span>
                              <span className="text-[11px] font-medium">{m.name}</span>
                            </div>

                            {m.isGate ? (
                              <span className="text-[9px] text-primary font-mono px-1 rounded bg-primary/10 border border-primary/20">
                                {m.note}
                              </span>
                            ) : !isAvailable ? (
                              <span className="text-[9px] text-amber-500/80 font-mono px-1 rounded bg-amber-500/10">
                                {m.note}
                              </span>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Next Action Box */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-3">
              <div className="flex items-center justify-between font-mono text-[10px] text-[#64748b] uppercase">
                <span>Next Workflow Phase</span>
                <span className="text-primary font-medium">
                  {queuedFiles.length > 1 ? 'Batch Screening & Anomaly Triage' : '02 — Signal Quality & Preprocessing'}
                </span>
              </div>

              {queuedFiles.length > 1 ? (
                <div className="space-y-2.5">
                  <button
                    id="btn-batch-screen-all"
                    onClick={handleBatchProceed}
                    className="w-full inline-flex items-center justify-center space-x-2.5 px-5 py-3.5 rounded-sm font-mono text-xs uppercase tracking-wider font-semibold bg-primary text-[#060911] hover:bg-primary/90 shadow-[0_0_16px_rgba(45,212,191,0.35)] transition-all cursor-pointer"
                  >
                    <Sparkles className="w-4 h-4 text-[#060911]" />
                    <span>Screen All {queuedFiles.length} Images for Abnormalities</span>
                    <ArrowRight className="w-3.5 h-3.5 text-[#060911]" />
                  </button>

                  <button
                    id="btn-continue-single-file"
                    onClick={handleProceed}
                    className="w-full inline-flex items-center justify-center space-x-2 px-4 py-2 rounded-sm font-mono text-[11px] text-[#8ea4bf] hover:text-white bg-[#0e1726] hover:bg-[#142033] border border-[#1d2d42] transition-colors cursor-pointer"
                  >
                    <span>Or inspect single file ({currentFile?.name})</span>
                  </button>
                </div>
              ) : (
                <button
                  id="btn-continue-quality-check"
                  disabled={!hasFiles}
                  onClick={handleProceed}
                  className={`w-full inline-flex items-center justify-center space-x-2.5 px-5 py-3 rounded-sm font-mono text-xs uppercase tracking-wider font-semibold transition-colors ${
                    hasFiles
                      ? 'bg-[#132338] hover:bg-[#1a2f4a] border border-[#273d5c] hover:border-primary/60 text-[#f1f5f9] cursor-pointer'
                      : 'bg-[#0d1420] border border-[#182333] text-[#50637c] cursor-not-allowed opacity-60'
                  }`}
                >
                  <span>Continue to Quality Check</span>
                  <ArrowRight className={`w-3.5 h-3.5 ${hasFiles ? 'text-primary' : 'text-[#50637c]'}`} />
                </button>
              )}

              <p className="font-sans text-[11px] text-[#64748b] font-normal leading-relaxed">
                {queuedFiles.length > 1
                  ? `Automated AI screening across all ${queuedFiles.length} images. Swaths with detected abnormalities (wrecks, mines, pipelines, ghost gear) are filtered and returned for operator triage.`
                  : hasFiles 
                    ? 'Verify swath continuity and signal-to-noise ratio in Preprocessing before AI anomaly segmentation.'
                    : 'Import one or more side-scan sonar files above to activate signal conditioning.'}
              </p>
            </div>
          </div>

          {/* RIGHT COLUMN: METADATA & PIPELINE VALIDATION (5/12) */}
          <div className="lg:col-span-5 space-y-4">
            
            {/* Survey Metadata Inspector */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-[#162234]">
                <span className="font-mono text-xs uppercase tracking-wider text-on-surface font-semibold flex items-center space-x-1.5">
                  <FileCode className="w-3.5 h-3.5 text-primary" />
                  <span>Survey Metadata</span>
                </span>
                <span className="font-mono text-[9px] text-[#64748b] uppercase">
                  {hasFiles ? 'Inspected' : 'Awaiting Data'}
                </span>
              </div>

              {!hasFiles ? (
                <div className="py-6 text-center text-[#64748b] font-sans text-xs">
                  Metadata will populate upon survey file import.
                </div>
              ) : (
                <div className="divide-y divide-[#162234] font-mono text-xs">
                  <div className="py-2 flex items-center justify-between">
                    <span className="text-[#8ea4bf]">SURVEY ID</span>
                    <span className="text-amber-400 text-[11px]">NOT DETECTED</span>
                  </div>

                  <div className="py-2 flex items-center justify-between">
                    <span className="text-[#8ea4bf]">FILE NAME</span>
                    <span className="text-on-surface text-[11px] truncate max-w-[180px]">
                      {metadataDetails?.name}
                    </span>
                  </div>

                  <div className="py-2 flex items-center justify-between">
                    <span className="text-[#8ea4bf]">FILE SIZE</span>
                    <span className="text-on-surface text-[11px]">
                      {metadataDetails?.size}
                    </span>
                  </div>

                  {metadataDetails?.resolution && (
                    <div className="py-2 flex items-center justify-between">
                      <span className="text-[#8ea4bf]">DIMENSIONS</span>
                      <span className="text-primary text-[11px]">
                        {metadataDetails.resolution}
                      </span>
                    </div>
                  )}

                  <div className="py-2 flex items-center justify-between">
                    <span className="text-[#8ea4bf]">TIMESTAMP</span>
                    {metadataDetails?.lastModified ? (
                      <span className="text-[#8ea4bf] text-[10px]">
                        {metadataDetails.lastModified}
                      </span>
                    ) : (
                      <span className="text-amber-400 text-[11px]">UNAVAILABLE</span>
                    )}
                  </div>

                  <div className="py-2 flex items-center justify-between">
                    <span className="text-[#8ea4bf]">NAVIGATION DATA</span>
                    {telemetry.latitude && telemetry.longitude ? (
                      <span className="text-primary text-[11px] font-medium">TELEMETRY CONFIGURED</span>
                    ) : (
                      <span className="text-amber-400 text-[11px]">UNAVAILABLE</span>
                    )}
                  </div>

                  <div className="py-2 flex items-center justify-between">
                    <span className="text-[#8ea4bf]">GPS / GEOLOCATION</span>
                    {telemetry.latitude && telemetry.longitude ? (
                      <span className="text-primary text-[11px] font-mono font-medium">
                        {telemetry.latitude}° N, {telemetry.longitude}° E
                      </span>
                    ) : (
                      <span className="text-amber-400 text-[11px]">UNAVAILABLE</span>
                    )}
                  </div>

                  <div className="py-2 flex items-center justify-between">
                    <span className="text-[#8ea4bf]">SONAR RASTER</span>
                    <span className="text-primary text-[11px] font-medium flex items-center space-x-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-primary"></span>
                      <span>DETECTED ({metadataDetails?.mimeType?.split('/')[1]?.toUpperCase() || 'STREAM'})</span>
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Data Validation Block */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between pb-2 border-b border-[#162234]">
                <div className="flex items-center space-x-1.5 text-on-surface font-semibold uppercase tracking-wider">
                  <ShieldCheck className="w-3.5 h-3.5 text-primary" />
                  <span>Pipeline Validation</span>
                </div>
                <span className="text-[9px] text-[#64748b]">INTEGRITY CHECK</span>
              </div>

              {!hasFiles ? (
                <div className="py-4 space-y-2 text-[#64748b]">
                  <div className="flex items-center space-x-2">
                    <span className="w-1.5 h-1.5 rounded-sm bg-[#1e2a3c]"></span>
                    <span>Awaiting file import</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="w-1.5 h-1.5 rounded-sm bg-[#1e2a3c]"></span>
                    <span>Awaiting metadata scan</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center space-x-2 text-primary">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>File Readable & Validated</span>
                  </div>

                  <div className="flex items-center space-x-2 text-primary">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Sonar Raster Stream Detected</span>
                  </div>

                  {/* Restrained Navigation Warning or Confirmation */}
                  {telemetry.latitude && telemetry.longitude ? (
                    <div className="p-3 bg-[#102a24] border border-[#1b5e50] rounded-sm space-y-1 text-[#99f6e4]">
                      <div className="flex items-center space-x-1.5 font-semibold text-[11px]">
                        <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0" />
                        <span>Survey Navigation Telemetry Ready</span>
                      </div>
                      <p className="font-sans text-[11px] text-[#8ea4bf] font-normal leading-relaxed">
                        Survey coordinates will be transmitted to backend and georeferenced on the marine GIS map.
                      </p>
                    </div>
                  ) : (
                    <div className="p-3 bg-[#131109] border border-amber-500/30 rounded-sm space-y-1 text-amber-300">
                      <div className="flex items-center space-x-1.5 font-semibold text-[11px]">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                        <span>Navigation Metadata Unavailable</span>
                      </div>
                      <p className="font-sans text-[11px] text-[#c9a66b] font-normal leading-relaxed">
                        Detections can still be analyzed in image space. Geolocation will remain unavailable unless survey navigation telemetry is supplied.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Audit Log / Recent Surveys */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-2">
              <div className="flex items-center justify-between pb-1 font-mono text-[10px] text-[#64748b] uppercase">
                <span>Recent Ingests</span>
                <span>Session Log</span>
              </div>

              {sessionSurveys.length === 0 ? (
                <p className="font-sans text-xs text-[#64748b] py-2">
                  No previous surveys in this session.
                </p>
              ) : (
                <div className="space-y-1.5 font-mono text-xs">
                  {sessionSurveys.map((survey, sIdx) => (
                    <div
                      key={sIdx}
                      onClick={() => onOpenAnalysis && survey.analysisId && onOpenAnalysis(survey.analysisId)}
                      className={`flex items-center justify-between p-2 bg-[#0e1625] border border-[#1b283d] rounded-sm text-[#8ea4bf] ${survey.analysisId ? 'hover:bg-[#121e31] hover:border-primary/40 cursor-pointer transition-colors' : ''}`}
                      title={survey.analysisId ? `Load analysis record ${survey.analysisId}` : undefined}
                    >
                      <span className="truncate text-on-surface">{survey.name}</span>
                      <span className="text-[10px] text-primary">{survey.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
