import React, { useState, useEffect } from 'react';
import { 
  Crosshair, 
  ZoomIn, 
  ZoomOut, 
  RotateCcw, 
  CheckCircle2, 
  AlertTriangle, 
  ArrowRight, 
  Globe, 
  Database,
  Split,
  Image as ImageIcon,
  Info
} from 'lucide-react';
import { soundFx } from '../../utils/audio';
import MarineGisMap from '../gis/MarineGisMap';
import { getFormattedDetections, MASTER_DETECTIONS } from '../../data/sharedDetections';
import { API_BASE_URL } from '../../services/api';

export default function WorkspaceView({ 
  onNavigate,
  selectedAnomalyId,
  onSelectAnomaly,
  surveyFile,
  anomalies = [],
  analysisResult = null
}) {
  // Genuine navigation metadata detection: only true if surveyFile/backend provides navigation telemetry
  const hasNavigationMetadata = Boolean(
    surveyFile?.hasNavigation || 
    surveyFile?.hasGps || 
    surveyFile?.navigationData || 
    (surveyFile?.latitude != null && surveyFile?.longitude != null) ||
    (analysisResult?.metadata?.latitude != null && analysisResult?.metadata?.longitude != null) ||
    (analysisResult?.metadata?.geolocation_available) ||
    (analysisResult?.geolocation?.latitude != null && analysisResult?.geolocation?.longitude != null) ||
    (anomalies && anomalies.length > 0 && anomalies.some(d => d.latitude != null && d.longitude != null))
  );

  // Active view tab: default to 'split' if navigation exists, or 'image' if image-only
  const [activeLayoutTab, setActiveLayoutTab] = useState(hasNavigationMetadata ? 'split' : 'image');

  // Sync layout tab when navigation availability changes
  useEffect(() => {
    setActiveLayoutTab(hasNavigationMetadata ? 'split' : 'image');
  }, [hasNavigationMetadata]);

  // Unified Detections adhering strictly to backend model schema (no mock fallback)
  const [detections, setDetections] = useState(() => (anomalies || []));
  const [selectedId, setSelectedId] = useState(selectedAnomalyId || (anomalies && anomalies.length > 0 ? anomalies[0].id : null));

  // Sonar Image-space Pan & Zoom
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const [downloadToast, setDownloadToast] = useState(null);
  const [imageUrl, setImageUrl] = useState(null);

  // Re-sync detections whenever anomalies change
  useEffect(() => {
    if (anomalies && anomalies.length > 0) {
      setDetections(anomalies);
      if (!selectedId || !anomalies.some(d => d.id === selectedId)) {
        setSelectedId(anomalies[0].id);
      }
    } else if (anomalies && anomalies.length === 0) {
      setDetections([]);
      setSelectedId(null);
    }
  }, [anomalies]);

  // Sync image URL: Prioritize local surveyFile for instant, bulletproof rendering
  useEffect(() => {
    if (surveyFile && (surveyFile instanceof File || surveyFile instanceof Blob)) {
      const url = URL.createObjectURL(surveyFile);
      setImageUrl(url);
      return () => URL.revokeObjectURL(url);
    } else if (analysisResult?.evidence_url) {
      const fullUrl = analysisResult.evidence_url.startsWith('http')
        ? analysisResult.evidence_url
        : `${API_BASE_URL}${analysisResult.evidence_url}`;
      setImageUrl(fullUrl);
    } else if (analysisResult?.analysis_id) {
      setImageUrl(`${API_BASE_URL}/api/v1/analysis/${analysisResult.analysis_id}/evidence`);
    } else {
      setImageUrl(null);
    }
  }, [surveyFile, analysisResult]);

  // Sync selectedId with prop
  useEffect(() => {
    if (selectedAnomalyId) {
      const match = detections.find(
        d => d.id === selectedAnomalyId || d.code === selectedAnomalyId
      );
      if (match) setSelectedId(match.id);
    }
  }, [selectedAnomalyId, detections]);

  const activeDetection = detections.find(d => d.id === selectedId) || detections[0] || null;

  const handleSelectDetection = (id) => {
    soundFx.playTargetLock();
    setSelectedId(id);
    if (onSelectAnomaly) {
      onSelectAnomaly(id);
    }
  };

  // Sonar Image Pan/Zoom handlers
  const handleMouseDown = (e) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
  };

  const handleMouseMove = (e) => {
    if (!isDragging) return;
    setPanOffset({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleZoomIn = () => {
    soundFx.playSonarPing(1300, 0.2);
    setZoomLevel(prev => Math.min(prev + 0.25, 2.5));
  };

  const handleZoomOut = () => {
    soundFx.playSonarPing(1100, 0.2);
    setZoomLevel(prev => Math.max(prev - 0.25, 0.75));
  };

  const handleResetView = () => {
    soundFx.playSonarPing(1000, 0.2);
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
  };

  // Export JSON Report
  const handleExportJSON = () => {
    soundFx.playTargetLock();
    const exportData = {
      surveySession: surveyFile ? surveyFile.name : (hasNavigationMetadata ? "SURVEY_TRANSECT_GIS" : "IMAGE_ONLY_SONAR_INPUT"),
      timestamp: new Date().toISOString(),
      navigationData: hasNavigationMetadata ? "AVAILABLE" : "NOT AVAILABLE",
      geolocationStatus: hasNavigationMetadata ? "AVAILABLE" : "UNAVAILABLE",
      coordinateReference: hasNavigationMetadata ? (activeDetection?.coordinateReference || "WGS 84 (Geographic 2D - EPSG:4326)") : "UNAVAILABLE",
      source: hasNavigationMetadata ? (activeDetection?.metadataSource || "Survey Towfish GPS Anchor") : "Image-only sonar input",
      methodologyNote: hasNavigationMetadata 
        ? "Detections mapped to geodetic coordinates via verified navigation stream."
        : "Geographic coordinates require navigation or survey metadata. Detections evaluated strictly in image space.",
      totalDetections: detections.length,
      detections: detections.map(d => ({
        id: d.id,
        code: d.code,
        class: d.class,
        confidence: `${d.confidence}%`,
        imagePosition: {
          xPercent: d.imagePosition.x,
          yPercent: d.imagePosition.y,
          display: d.imagePosition.display
        },
        bbox: d.bbox,
        geolocationStatus: hasNavigationMetadata ? "AVAILABLE" : "UNAVAILABLE",
        latitude: d.latitude,
        longitude: d.longitude,
        coordinateReference: d.coordinateReference,
        dimensions: d.dimensions,
        acousticShadow: d.acousticShadow || d.shadowLength,
        status: d.reviewStatus || "PENDING REVIEW",
        reviewStatus: d.reviewStatus || "PENDING REVIEW",
        acousticFeature: d.acousticFeature
      }))
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SONAROPS_EVIDENCE_${hasNavigationMetadata ? 'GIS' : 'IMAGE_SPACE'}_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);

    setDownloadToast(`Evidence dossier exported (JSON) — ${hasNavigationMetadata ? 'GIS Georeferenced' : 'Image Space'}`);
    setTimeout(() => setDownloadToast(null), 3000);
  };

  // Export CSV Report
  const handleExportCSV = () => {
    soundFx.playTargetLock();
    const headers = "Detection_ID,Classification,Confidence_Pct,Image_Pos_X,Image_Pos_Y,Latitude,Longitude,CRS,Dimensions,Acoustic_Shadow,Review_Status,Source\n";
    const rows = detections.map(d => 
      `"${d.id}","${d.class}",${d.confidence},"${d.imagePosition.x}%","${d.imagePosition.y}%","${d.latitude !== null ? d.latitude : 'UNAVAILABLE'}","${d.longitude !== null ? d.longitude : 'UNAVAILABLE'}","${d.coordinateReference}","${d.dimensions}","${d.acousticShadow || d.shadowLength}","${d.reviewStatus || 'PENDING REVIEW'}","${d.metadataSource}"`
    ).join("\n");

    const blob = new Blob([headers + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SONAROPS_EVIDENCE_${hasNavigationMetadata ? 'GIS' : 'IMAGE_SPACE'}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);

    setDownloadToast(`Evidence dataset exported (CSV) — ${hasNavigationMetadata ? 'GIS Georeferenced' : 'Image Space'}`);
    setTimeout(() => setDownloadToast(null), 3000);
  };

  const handleGenerateReport = () => {
    soundFx.playTargetLock();
    if (onNavigate) {
      onNavigate('view-summary');
    }
  };

  return (
    <section className="relative w-full h-[calc(100vh-3.5rem)] overflow-hidden bg-[#060911] text-[#f1f5f9] select-none flex flex-col justify-between">
      {/* Toast Notification */}
      {downloadToast && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 bg-[#0b111e]/98 border border-[#22354e] text-primary font-mono text-xs px-4 py-2 rounded-sm flex items-center space-x-2 shadow-lg">
          <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
          <span>{downloadToast}</span>
        </div>
      )}

      {/* ======================================================== */}
      {/* 1. HEADER & WORKFLOW SEQUENCE                            */}
      {/* ======================================================== */}
      <div className="relative z-30 px-4 sm:px-6 lg:px-8 py-2.5 border-b border-[#162234] bg-[#070b14]/95 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <div className="flex items-center space-x-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-sm bg-primary"></span>
            <span className="font-mono text-xs tracking-[0.2em] text-[#8ea4bf] uppercase font-semibold">
              04 — EVIDENCE / GEOLOCATION
            </span>
            <span className="text-[#33465e]">|</span>
            <span className={`font-mono text-[9px] uppercase font-medium px-2 py-0.5 rounded-sm border ${
              hasNavigationMetadata 
                ? 'bg-[#102a24] border-[#1b5e50] text-[#99f6e4]' 
                : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
            }`}>
              {hasNavigationMetadata ? 'GEOSPATIAL & IMAGE EVIDENCE' : 'IMAGE-SPACE EVIDENCE ONLY'}
            </span>
          </div>

          <h1 className="text-xl sm:text-2xl font-headline tracking-tight text-on-surface font-normal">
            {hasNavigationMetadata ? 'Geospatial survey localization & acoustic evidence.' : 'Acoustic evidence & image-space localization.'}
          </h1>
          <p className="font-sans text-xs text-[#94a3b8] max-w-xl font-normal leading-tight">
            {hasNavigationMetadata 
              ? 'Real-time georeferenced coordinates derived from survey navigation stream.' 
              : 'Review detection targets in sonar image space. Geographic coordinates require survey navigation metadata.'}
          </p>
        </div>

        {/* View Mode Tabs, Navigation Data Status Badge & Exports */}
        <div className="flex flex-wrap items-center gap-2.5 shrink-0 font-mono text-[10px]">
          {/* Layout Tab Selector */}
          <div className="flex bg-[#0b111e] border border-[#1a2638] rounded-sm p-0.5">
            <button
              onClick={() => setActiveLayoutTab('split')}
              className={`px-2.5 py-1 rounded-sm flex items-center space-x-1.5 transition-colors cursor-pointer ${
                activeLayoutTab === 'split' ? 'bg-[#101b2c] text-primary font-semibold' : 'text-[#8ea4bf] hover:text-[#f8fafc]'
              }`}
            >
              <Split className="w-3 h-3" />
              <span>SPLIT</span>
            </button>
            <button
              onClick={() => setActiveLayoutTab('gis')}
              className={`px-2.5 py-1 rounded-sm flex items-center space-x-1.5 transition-colors cursor-pointer ${
                activeLayoutTab === 'gis' ? 'bg-[#101b2c] text-primary font-semibold' : 'text-[#8ea4bf] hover:text-[#f8fafc]'
              }`}
            >
              <Globe className="w-3 h-3" />
              <span>GIS MAP</span>
            </button>
            <button
              onClick={() => setActiveLayoutTab('image')}
              className={`px-2.5 py-1 rounded-sm flex items-center space-x-1.5 transition-colors cursor-pointer ${
                activeLayoutTab === 'image' ? 'bg-[#101b2c] text-primary font-semibold' : 'text-[#8ea4bf] hover:text-[#f8fafc]'
              }`}
            >
              <ImageIcon className="w-3 h-3" />
              <span>SONAR SWATH</span>
            </button>
          </div>

          {/* Dynamic Navigation Data Status Badge (Truthful & Non-Hardcoded) */}
          <div className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-sm border ${
            hasNavigationMetadata
              ? 'border-[#1b5e50] bg-[#102a24] text-[#99f6e4]'
              : 'border-[#1b283d] bg-[#0b111e] text-[#8ea4bf]'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${hasNavigationMetadata ? 'bg-primary' : 'bg-amber-400/80'}`}></span>
            <span>NAVIGATION DATA: {hasNavigationMetadata ? 'AVAILABLE' : 'NOT AVAILABLE'}</span>
          </div>

          {/* Exports & Proceed */}
          <div className="flex items-center space-x-1.5">
            <button
              onClick={handleExportJSON}
              title="Export Evidence Dossier (JSON)"
              className="px-2.5 py-1.5 bg-[#0b111e] hover:bg-[#131f32] border border-[#1a2638] text-[#cbd5e1] rounded-sm transition-colors cursor-pointer"
            >
              JSON
            </button>
            <button
              onClick={handleExportCSV}
              title="Export Evidence Dataset (CSV)"
              className="px-2.5 py-1.5 bg-[#0b111e] hover:bg-[#131f32] border border-[#1a2638] text-[#cbd5e1] rounded-sm transition-colors cursor-pointer"
            >
              CSV
            </button>
            <button
              onClick={handleGenerateReport}
              className="px-3 py-1.5 bg-[#132338] hover:bg-[#1a2f4a] border border-[#273d5c] hover:border-primary/60 text-[#f1f5f9] rounded-sm transition-colors cursor-pointer flex items-center space-x-1 font-semibold"
            >
              <span>REPORT</span>
              <ArrowRight className="w-3 h-3 text-primary" />
            </button>
          </div>
        </div>
      </div>

      {/* ======================================================== */}
      {/* 2. MAIN WORKSPACE CONTENT: DUAL / SPLIT LAYOUT           */}
      {/* ======================================================== */}
      <div className="relative flex-1 w-full overflow-hidden p-3 sm:p-4 grid grid-cols-1 lg:grid-cols-12 gap-3 min-h-0">
        
        {/* ======================================================== */}
        {/* LEFT AREA: GIS MAP OR IMAGE SWATH                        */}
        {/* ======================================================== */}
        <div className={`${activeLayoutTab === 'image' ? 'hidden' : activeLayoutTab === 'gis' ? 'lg:col-span-8 h-full' : 'lg:col-span-8 flex flex-col gap-3 h-full overflow-hidden'}`}>
          
          {/* UPPER SECTION: THE GIS MAP (OR HONEST EMPTY STATE) */}
          <div className={`${activeLayoutTab === 'gis' ? 'h-full' : 'h-[55%] min-h-[220px] relative'}`}>
            {hasNavigationMetadata ? (
              /* A. REAL GIS MAP WITH LEAFLET (Active when navigation stream exists) */
              <MarineGisMap
                detections={detections}
                selectedId={selectedId}
                onSelectDetection={handleSelectDetection}
                surveyLocation={analysisResult?.metadata || analysisResult?.geolocation || surveyFile}
              />
            ) : (
              /* B. HONEST EMPTY-STATE WHEN GEOLOCATION IS UNAVAILABLE */
              <div className="w-full h-full bg-[#040812] border border-[#1a2638] rounded-sm p-6 flex flex-col items-center justify-center text-center space-y-4 select-none">
                <div className="w-12 h-12 rounded-sm border border-[#1a2638] bg-[#090f1a] flex items-center justify-center text-[#7d93ad]">
                  <Globe className="w-6 h-6 stroke-[1.5]" />
                </div>
                
                <div className="space-y-2 max-w-md">
                  <span className="font-mono text-[10px] tracking-[0.2em] text-[#7d93ad] uppercase font-semibold block">
                    GEOSPATIAL VIEW
                  </span>
                  <h3 className="text-base sm:text-lg font-headline text-on-surface font-semibold">
                    LOCATION DATA NOT AVAILABLE
                  </h3>
                  <p className="font-sans text-xs text-[#94a3b8] leading-relaxed">
                    No geographic coordinates are available for this sonar input.
                  </p>
                  <p className="font-sans text-xs text-[#64748b]">
                    Review detections using image-space evidence.
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    onClick={() => setActiveLayoutTab('image')}
                    className="px-4 py-2 rounded-sm bg-[#101b2c] hover:bg-[#16253c] border border-[#22354e] text-primary font-mono text-xs uppercase tracking-wider font-semibold transition-colors cursor-pointer"
                  >
                    VIEW IMAGE EVIDENCE
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* LOWER SECTION: SONAR IMAGE / ROI EVIDENCE SWATH */}
          {activeLayoutTab === 'split' && (
            <div className="flex-1 min-h-[180px] bg-[#02050c] border border-[#1a2638] rounded-sm relative overflow-hidden flex flex-col">
              {/* Header Bar */}
              <div className="px-3 py-1.5 bg-[#070d18] border-b border-[#162234] flex items-center justify-between text-xs font-mono shrink-0">
                <div className="flex items-center space-x-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary"></span>
                  <span className="text-[#f8fafc] text-[11px] font-semibold">SONAR IMAGE EVIDENCE</span>
                  <span className="text-[#33465e]">|</span>
                  <span className="text-[#64748b] text-[10px]">
                    {surveyFile?.name || 'RAW ACOUSTIC SWATH'}
                  </span>
                </div>

                <div className="flex items-center space-x-1">
                  <button onClick={handleZoomIn} title="Zoom In" className="p-1 hover:text-primary transition-colors cursor-pointer"><ZoomIn className="w-3.5 h-3.5" /></button>
                  <button onClick={handleZoomOut} title="Zoom Out" className="p-1 hover:text-primary transition-colors cursor-pointer"><ZoomOut className="w-3.5 h-3.5" /></button>
                  <button onClick={handleResetView} title="Reset Pan/Zoom" className="p-1 hover:text-primary transition-colors cursor-pointer"><RotateCcw className="w-3.5 h-3.5" /></button>
                </div>
              </div>

              {/* Viewport with Zoom and Pan */}
              <div
                className="relative flex-1 w-full overflow-hidden cursor-grab active:cursor-grabbing bg-[#02050c]"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
              >
                <div
                  className="absolute inset-0 transition-transform duration-75"
                  style={{
                    transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
                    transformOrigin: '50% 50%'
                  }}
                >
                  {/* Acoustic Background Matrix */}
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
                      className="absolute inset-0 w-full h-full object-cover opacity-85 contrast-125 pointer-events-none"
                      onError={(e) => {
                        if (surveyFile && (surveyFile instanceof File || surveyFile instanceof Blob)) {
                          e.target.src = URL.createObjectURL(surveyFile);
                        } else {
                          e.target.style.display = 'none';
                        }
                      }}
                    />
                  )}

                  {/* Nadir Water Column */}
                  <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-4 bg-[#010408] border-x border-[#1a2638] flex flex-col justify-between items-center py-2 font-mono text-[8px] text-[#50637c] pointer-events-none z-10">
                    <span>NADIR</span>
                    <span className="text-primary font-bold">0m</span>
                    <span>NADIR</span>
                  </div>

                  {/* Range Boundaries */}
                  <div className="absolute top-1.5 inset-x-4 flex justify-between font-mono text-[9px] text-[#50637c] pointer-events-none z-10">
                    <span>PORT (-75m)</span>
                    <span>STARBOARD (+75m)</span>
                  </div>

                  {/* Anomaly Bounding Boxes */}
                  {detections.map((det) => {
                    const isSelected = det.id === selectedId;
                    return (
                      <div
                        key={det.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelectDetection(det.id);
                        }}
                        style={{
                          left: `${det.bbox.x}%`,
                          top: `${det.bbox.y}%`,
                          width: `${det.bbox.w}%`,
                          height: `${det.bbox.h}%`
                        }}
                        className={`absolute cursor-pointer transition-all z-20 ${
                          isSelected
                            ? 'border-2 border-primary bg-primary/15 shadow-[0_0_12px_rgba(45,212,191,0.4)]'
                            : 'border border-primary/40 hover:border-primary bg-transparent'
                        }`}
                      >
                        <div className="absolute -top-5 left-0 flex items-center space-x-1 font-mono text-[9px] bg-[#060911]/95 px-1.5 py-0.2 rounded-sm border border-[#1a2638] text-on-surface whitespace-nowrap">
                          <span className="font-bold text-primary">{det.code}</span>
                          <span className="text-[#8ea4bf]">{det.className}</span>
                          <span className="text-[#33465e]">|</span>
                          <span className="text-white font-medium">{det.confidence}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* FULL IMAGE MODE ONLY (When selected in layout tabs) */}
        {activeLayoutTab === 'image' && (
          <div className="lg:col-span-8 h-full bg-[#02050c] border border-[#1a2638] rounded-sm relative overflow-hidden flex flex-col">
            <div className="px-3 py-2 bg-[#070d18] border-b border-[#162234] flex items-center justify-between text-xs font-mono shrink-0">
              <div className="flex items-center space-x-2">
                <span className="w-1.5 h-1.5 rounded-full bg-primary"></span>
                <span className="text-[#f8fafc] text-xs font-semibold">ACOUSTIC SWATH · FULL RESOLUTION IMAGE SPACE</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <button onClick={handleZoomIn} className="px-2 py-0.5 bg-[#0b111e] border border-[#1a2638] rounded-sm text-xs cursor-pointer">+</button>
                <button onClick={handleZoomOut} className="px-2 py-0.5 bg-[#0b111e] border border-[#1a2638] rounded-sm text-xs cursor-pointer">-</button>
                <button onClick={handleResetView} className="px-2 py-0.5 bg-[#0b111e] border border-[#1a2638] rounded-sm text-xs cursor-pointer">RESET</button>
              </div>
            </div>

            <div
              className="relative flex-1 w-full overflow-hidden cursor-grab active:cursor-grabbing bg-[#02050c]"
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
              <div
                className="absolute inset-0 transition-transform duration-75"
                style={{
                  transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
                  transformOrigin: '50% 50%'
                }}
              >
                {imageUrl && (
                  <img 
                    src={imageUrl} 
                    alt="Side-Scan Sonar Swath" 
                    className="absolute inset-0 w-full h-full object-cover opacity-85 contrast-125 pointer-events-none"
                    onError={(e) => {
                      if (surveyFile && (surveyFile instanceof File || surveyFile instanceof Blob)) {
                        e.target.src = URL.createObjectURL(surveyFile);
                      } else {
                        e.target.style.display = 'none';
                      }
                    }}
                  />
                )}
                {/* Nadir Water Column */}
                <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-5 bg-[#010408] border-x border-[#1a2638] flex flex-col justify-between items-center py-4 font-mono text-[9px] text-[#50637c] pointer-events-none z-10">
                  <span>NADIR</span>
                  <span className="text-primary font-bold">0m</span>
                  <span>NADIR</span>
                </div>
                {/* Bounding boxes */}
                {detections.map((det) => {
                  const isSelected = det.id === selectedId;
                  return (
                    <div
                      key={det.id}
                      onClick={() => handleSelectDetection(det.id)}
                      style={{
                        left: `${det.bbox.x}%`,
                        top: `${det.bbox.y}%`,
                        width: `${det.bbox.w}%`,
                        height: `${det.bbox.h}%`
                      }}
                      className={`absolute cursor-pointer transition-all z-20 ${
                        isSelected
                          ? 'border-2 border-primary bg-primary/20 shadow-[0_0_14px_rgba(45,212,191,0.5)]'
                          : 'border border-primary/40 hover:border-primary bg-transparent'
                      }`}
                    >
                      <div className="absolute -top-5 left-0 flex items-center space-x-1 font-mono text-[9px] bg-[#060911]/95 px-1.5 py-0.2 rounded-sm border border-[#1a2638] text-on-surface whitespace-nowrap">
                        <span className="font-bold text-primary">{det.code}</span>
                        <span className="text-[#8ea4bf]">{det.className}</span>
                        <span className="text-[#33465e]">|</span>
                        <span className="text-white font-medium">{det.confidence}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* RIGHT AREA: SELECTED DETECTION & EVIDENCE DETAILS        */}
        {/* ======================================================== */}
        <div className="lg:col-span-4 h-full flex flex-col justify-between space-y-3 overflow-y-auto pr-0.5">
          
          {/* Main Evidence Card */}
          <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-3 font-mono text-xs">
            {/* Header Stage Tracker: Adapts to Image-Only vs Geolocation */}
            <div className="flex items-center space-x-1 text-[9px] text-[#64748b] uppercase tracking-wider pb-2 border-b border-[#162234]">
              <span className="text-primary font-semibold">SONAR IMAGE</span>
              <span>→</span>
              <span className="text-primary font-semibold">DETECTION</span>
              <span>→</span>
              {hasNavigationMetadata ? (
                <>
                  <span className="text-primary font-semibold">GEOLOCATION</span>
                  <span>→</span>
                  <span className="text-[#cbd5e1] font-bold">EVIDENCE</span>
                </>
              ) : (
                <span className="text-[#cbd5e1] font-bold">IMAGE-SPACE EVIDENCE</span>
              )}
            </div>

            {/* Target Title & Neutral Review Status (MODEL RESULT / PENDING REVIEW) */}
            {!activeDetection ? (
              <div className="py-12 text-center space-y-2 font-mono">
                <CheckCircle2 className="w-7 h-7 text-primary mx-auto opacity-75" />
                <h3 className="text-sm font-bold text-on-surface uppercase">No Targets Detected</h3>
                <p className="font-sans text-xs text-[#8ea4bf] max-w-xs mx-auto">
                  No acoustic anomalies were identified in this survey swath.
                </p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[10px] text-primary block font-semibold">
                      DETECTION #{activeDetection.code}
                    </span>
                    <h3 className="text-base font-bold text-on-surface">
                      {activeDetection.className}
                    </h3>
                  </div>
                  <span className="px-2 py-0.5 rounded-sm text-[10px] font-semibold tracking-wider border bg-[#101b2c] text-[#8ea4bf] border-[#22354e]">
                    {activeDetection.reviewStatus || "PENDING REVIEW"}
                  </span>
                </div>

                {/* Strict Scientific Attribute Table */}
                <div className="divide-y divide-[#162234] text-[11px]">
                  <div className="py-1.5 flex justify-between">
                    <span className="text-[#8ea4bf]">Confidence</span>
                    <span className="text-primary font-bold">{activeDetection.confidence}%</span>
                  </div>
                  <div className="py-1.5 flex justify-between">
                    <span className="text-[#8ea4bf]">Source</span>
                    <span className="text-[#cbd5e1]">{activeDetection.metadataSource}</span>
                  </div>

                  {/* IMAGE POSITION: Explicitly labeled as Image Position */}
                  <div className="py-1.5 flex justify-between">
                    <span className="text-[#8ea4bf]">Image Position</span>
                    <span className="text-[#f1f5f9] font-mono">
                      X: {activeDetection.imagePosition?.x ?? 0}%, Y: {activeDetection.imagePosition?.y ?? 0}% (IMAGE POSITION)
                    </span>
                  </div>

                  <div className="py-1.5 flex justify-between">
                    <span className="text-[#8ea4bf]">Estimated Dimensions</span>
                    <span className="text-[#f1f5f9]">{activeDetection.dimensions}</span>
                  </div>
                  <div className="py-1.5 flex justify-between">
                    <span className="text-[#8ea4bf]">Acoustic Shadow</span>
                    <span className="text-[#f1f5f9]">{activeDetection.acousticShadow || activeDetection.shadowLength}</span>
                  </div>

                  {/* GEOLOCATION: REAL COORDINATES VS HONEST UNAVAILABLE STATE */}
                  <div className="py-2 space-y-1 bg-[#070d18] -mx-4 px-4 border-y border-[#162234]">
                    <div className="flex justify-between items-center">
                      <span className="text-[#8ea4bf] text-[10px] uppercase font-semibold">GEOLOCATION</span>
                      <span className={`text-[10px] font-bold ${hasNavigationMetadata ? 'text-[#99f6e4]' : 'text-amber-400'}`}>
                        {hasNavigationMetadata ? 'AVAILABLE' : 'UNAVAILABLE'}
                      </span>
                    </div>

                    {hasNavigationMetadata && activeDetection.latitude ? (
                      <div className="space-y-1 pt-1 text-[11px]">
                        <div className="flex justify-between">
                          <span className="text-[#64748b]">Latitude:</span>
                          <span className="text-primary font-mono font-medium">{activeDetection.latitude.toFixed(4)}° N</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#64748b]">Longitude:</span>
                          <span className="text-primary font-mono font-medium">{activeDetection.longitude.toFixed(4)}° E</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#64748b]">Coordinate Ref:</span>
                          <span className="text-[#8ea4bf] font-mono text-[10px]">{activeDetection.coordinateReference}</span>
                        </div>
                      </div>
                    ) : (
                      <div className="pt-1 text-[10px] text-[#c9a66b] font-sans leading-relaxed">
                        Reason: No navigation or survey metadata was provided with this input.
                      </div>
                    )}
                  </div>

                  {/* Acoustic Feature Description */}
                  <div className="py-2 space-y-1">
                    <span className="text-[#8ea4bf] text-[10px] uppercase block">Acoustic Signature</span>
                    <p className="font-sans text-[11px] text-[#94a3b8] leading-relaxed">
                      {activeDetection.acousticFeature}
                    </p>
                  </div>
                </div>

                {/* Correlated Sonar ROI Crop */}
                <div className="pt-1">
                  <span className="text-[10px] font-mono text-[#8ea4bf] block mb-1">
                    CORRELATED SONAR ROI (EVIDENCE CROP):
                  </span>
                  <div className="relative h-20 bg-[#020509] border border-[#1a2638] rounded-sm overflow-hidden flex items-center justify-between p-2.5">
                    <div 
                      className="absolute inset-0 opacity-60 pointer-events-none"
                  style={{
                    backgroundImage: 'linear-gradient(to right, #020509 0%, #0c1a2f 50%, #020509 100%), repeating-radial-gradient(circle at 50% 50%, transparent 0, transparent 2px, rgba(56, 189, 248, 0.15) 3px, transparent 4px)',
                    backgroundSize: '100% 100%, 12px 12px'
                  }}
                />
                <div className="relative z-10 w-full flex items-center justify-between text-[10px]">
                  <div className="space-y-0.5">
                    <span className="text-primary font-bold block">{activeDetection.id} · SPECULAR ECHO</span>
                    <span className="text-[#8ea4bf] text-[9px] block max-w-[210px] truncate">
                      {activeDetection.acousticFeature}
                    </span>
                  </div>
                  <div className="w-10 h-10 border border-primary/60 rounded bg-primary/10 flex items-center justify-center text-primary shrink-0 ml-2">
                    <Crosshair className="w-5 h-5 animate-pulse" />
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

          {/* Bottom Action Checklist Notice */}
          <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3 font-mono text-[10px] text-[#8ea4bf] space-y-1.5">
            <div className="flex justify-between items-center text-on-surface font-semibold uppercase">
              <span>WORKFLOW STAGE</span>
              <span className="text-primary">STAGE 04 COMPLETE</span>
            </div>
            <p className="font-sans text-[11px] text-[#64748b] leading-tight">
              Ready to consolidate anomaly classification register and export final dossier in Stage 05 Report.
            </p>
          </div>
        </div>
      </div>

      {/* ======================================================== */}
      {/* 3. BOTTOM DETECTION SELECTOR TRAY (CROSS-PAGE LINKING)   */}
      {/* ======================================================== */}
      <div className="px-4 sm:px-6 lg:px-8 py-2 bg-[#070b14] border-t border-[#162234] z-30 shrink-0">
        <div className="flex items-center justify-between mb-1.5 font-mono text-[10px]">
          <span className="text-[#8ea4bf] uppercase tracking-wider flex items-center space-x-1.5">
            <Database className="w-3 h-3 text-primary" />
            <span>ANOMALY EVIDENCE REGISTER · {detections.length} TARGETS</span>
          </span>
          <span className="text-[#50637c] hidden sm:inline">
            SELECT TO SYNCHRONIZE MAP &amp; SONAR ROI
          </span>
        </div>

        {detections.length === 0 ? (
          <div className="py-2.5 px-3 bg-[#090f1a] border border-[#162234] rounded-sm text-center font-mono text-[11px] text-[#64748b]">
            No acoustic anomaly targets registered for this survey swath.
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {detections.map((det) => {
              const isSelected = det.id === selectedId;
              return (
                <button
                  key={det.id}
                  onClick={() => handleSelectDetection(det.id)}
                  className={`p-2 rounded-sm text-left transition-colors font-mono border cursor-pointer ${
                    isSelected
                      ? 'border-primary bg-[#101b2c] text-on-surface shadow-sm'
                      : 'border-[#162234] bg-[#090f1a] hover:border-[#22354e] text-[#8ea4bf]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[10px] font-bold text-primary">#{det.code} {det.className}</span>
                    <span className="text-[9px] font-semibold text-white">{det.confidence}%</span>
                  </div>
                  <div className="flex items-center justify-between text-[9px] text-[#64748b]">
                    <span>POS: {det.imagePosition?.x ?? 0}%, {det.imagePosition?.y ?? 0}%</span>
                    <span className={hasNavigationMetadata ? 'text-[#99f6e4]' : 'text-amber-400/90'}>
                      {hasNavigationMetadata ? 'GEO: LINKED' : 'GEO: N/A'}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
