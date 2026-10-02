import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  Download, 
  FileSpreadsheet, 
  Printer, 
  CheckCircle2, 
  ArrowRight, 
  ShieldCheck, 
  Crosshair,
  FileCheck,
  Info
} from 'lucide-react';
import { soundFx } from '../../utils/audio';
import { 
  DEMO_REPORT_DETECTIONS, 
  computeReportSummary, 
  REPORT_READINESS_SPEC,
  buildJSONExportPayload,
  buildCSVExportPayload
} from '../../data/reportData';
import { API_BASE_URL } from '../../services/api';

export default function ReportView({ 
  anomalies, 
  selectedAnomalyId,
  onSelectAnomaly, 
  onNavigate,
  surveyFile,
  analysisResult = null
}) {
  const [detections, setDetections] = useState(() => (
    anomalies && anomalies.length > 0 ? anomalies : []
  ));
  const [selectedId, setSelectedId] = useState(() => (anomalies && anomalies.length > 0 ? (anomalies[0].code || '01') : null));
  const [analystNotes, setAnalystNotes] = useState('');
  const [downloadToast, setDownloadToast] = useState(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState(null);

  // Sync detections whenever real backend anomalies change
  useEffect(() => {
    if (anomalies && anomalies.length > 0) {
      const reportItems = anomalies.map((item, idx) => ({
        detection_id: item.code || String(idx + 1).padStart(2, '0'),
        raw_id: item.id || `DET-${item.code}`,
        target_name: item.type || item.className || 'Acoustic Anomaly',
        classification: item.className || item.class || 'ANOMALY',
        class_name: item.className || item.class || 'ANOMALY',
        confidence: item.confidence_raw || (item.confidence > 1 ? item.confidence / 100 : item.confidence),
        confidence_display: `${item.confidence}%`,
        confidence_score: item.confidence,
        priority: item.priority || 'LOW',
        priority_reason: item.priority_reason || '',
        review_status: item.review_status || item.status || 'PENDING REVIEW',
        status: item.review_status || item.status || 'PENDING REVIEW',
        evidence_status: item.evidence_status || 'AVAILABLE',
        model: item.model || 'unknown',
        geolocation_status: (item.latitude != null && item.longitude != null) ? 'AVAILABLE' : 'UNAVAILABLE',
        navigation_metadata: (item.latitude != null && item.longitude != null) ? 'SURVEY STREAM' : 'NOT DETECTED',
        lat: item.latitude != null ? `${Number(item.latitude).toFixed(4)}° N` : 'UNAVAILABLE',
        lon: item.longitude != null ? `${Number(item.longitude).toFixed(4)}° E` : 'UNAVAILABLE',
        crs: item.coordinateReference || 'UNAVAILABLE',
        image_position: item.imagePosition || {
          display: `X: ${item.box?.x ?? 0}%, Y: ${item.box?.y ?? 0}%`
        },
        image_x: `${item.imagePosition?.x ?? item.box?.x ?? 0}%`,
        image_y: `${item.imagePosition?.y ?? item.box?.y ?? 0}%`,
        dimension_estimate: item.dimensions || 'N/A',
        acoustic_shadow_len: item.acousticShadow || item.shadowLength || 'N/A',
        acoustic_feature: item.acousticFeature || 'Acoustic reflector',
        source_sensor: item.metadataSource || 'Side-Scan Sonar ML Pipeline',
        source: item.metadataSource || 'Side-Scan Sonar ML Pipeline',
        evidence_image: item.evidenceImage || (analysisResult?.evidence_url ? `${API_BASE_URL}${analysisResult.evidence_url}` : null),
        ...item
      }));
      setDetections(reportItems);
    } else if (anomalies && anomalies.length === 0) {
      setDetections([]);
      setSelectedId(null);
    }
  }, [anomalies, analysisResult]);

  useEffect(() => {
    if (surveyFile && (surveyFile instanceof File || surveyFile instanceof Blob)) {
      const url = URL.createObjectURL(surveyFile);
      setUploadedImageUrl(url);
      return () => URL.revokeObjectURL(url);
    } else if (analysisResult?.evidence_url) {
      const fullUrl = analysisResult.evidence_url.startsWith('http')
        ? analysisResult.evidence_url
        : `${API_BASE_URL}${analysisResult.evidence_url}`;
      setUploadedImageUrl(fullUrl);
    } else if (analysisResult?.analysis_id) {
      setUploadedImageUrl(`${API_BASE_URL}/api/v1/analysis/${analysisResult.analysis_id}/evidence`);
    } else {
      setUploadedImageUrl(null);
    }
  }, [surveyFile, analysisResult]);

  useEffect(() => {
    if (selectedAnomalyId) {
      const match = detections.find(d => d.detection_id === selectedAnomalyId || d.raw_id === selectedAnomalyId);
      if (match) setSelectedId(match.detection_id);
    }
  }, [selectedAnomalyId, detections]);

  const summary = computeReportSummary(detections);
  const activeDetection = detections.find(d => d.detection_id === selectedId || d.raw_id === selectedId) || detections[0] || null;

  const handleSelectRow = (det) => {
    soundFx.playTargetLock();
    setSelectedId(det.detection_id);
    if (onSelectAnomaly) {
      onSelectAnomaly(det.raw_id || det.detection_id);
    }
  };

  const handleExportJSON = () => {
    soundFx.playTargetLock();
    const payload = buildJSONExportPayload(detections, analystNotes, surveyFile);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `SONAROPS_Anomaly_Report_${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);

    setDownloadToast("Structured JSON dossier exported.");
    setTimeout(() => setDownloadToast(null), 3000);
  };

  const handleExportCSV = () => {
    soundFx.playTargetLock();
    const csvContent = buildCSVExportPayload(detections, analystNotes);
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `SONAROPS_Anomaly_Report_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);

    setDownloadToast("Hydrographic CSV dataset exported.");
    setTimeout(() => setDownloadToast(null), 3000);
  };

  const handleGeneratePDF = () => {
    soundFx.playSonarPing(1400, 0.5);
    window.print();
  };

  return (
    <section className="relative w-full h-[calc(100vh-3.5rem)] overflow-y-auto bg-[#060911] text-[#f1f5f9] select-none flex flex-col justify-between">
      {/* Print Stylesheet for Official Dossiers */}
      <style>{`
        @media print {
          body {
            background-color: #ffffff !important;
            color: #0f172a !important;
          }
          header, nav, button, .no-print {
            display: none !important;
          }
          .printable-report {
            background: #ffffff !important;
            color: #0f172a !important;
            padding: 0 !important;
          }
          table {
            border-collapse: collapse;
            width: 100%;
          }
          th, td {
            border: 1px solid #cbd5e1 !important;
            color: #0f172a !important;
            padding: 8px !important;
          }
          th {
            background-color: #f1f5f9 !important;
          }
        }
      `}</style>

      {/* Floating Action Confirmation Toast */}
      {downloadToast && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 bg-[#0b111e]/98 border border-[#22354e] text-primary font-mono text-xs px-4 py-2 rounded-sm flex items-center space-x-2 shadow-lg">
          <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
          <span>{downloadToast}</span>
        </div>
      )}

      {/* ======================================================== */}
      {/* 1. SECTION HEADER & WORKFLOW SEQUENCE                    */}
      {/* ======================================================== */}
      <div className="relative z-30 px-4 sm:px-6 lg:px-8 pt-3 pb-2.5 border-b border-[#162234] bg-[#070b14]/95 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-sm bg-primary"></span>
            <span className="font-mono text-xs tracking-[0.2em] text-[#8ea4bf] uppercase font-semibold">
              05 — ANOMALY REPORT
            </span>
            <span className="text-[#33465e]">|</span>
            <span className="font-mono text-[9px] uppercase font-medium px-2 py-0.5 rounded-sm border border-primary/40 bg-primary/10 text-primary">
              FINAL OUTPUT
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-headline tracking-tight text-on-surface font-normal">
            Turn detections into evidence.
          </h1>
          <p className="font-sans text-xs text-[#94a3b8] max-w-2xl font-normal">
            Review detected anomalies, available location evidence, and export the survey results.
          </p>
        </div>

        {/* Workflow Sequence Rail */}
        <div className="flex items-center space-x-3 shrink-0">
          <div className="hidden lg:flex items-center space-x-2 font-mono text-[10px] text-[#64748b]">
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
            <button 
              onClick={() => onNavigate && onNavigate('view-detections')}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              03 DETECTION
            </button>
            <span className="text-[#33465e]">→</span>
            <button 
              onClick={() => onNavigate && onNavigate('view-workspace')}
              className="hover:text-primary transition-colors cursor-pointer"
            >
              04 EVIDENCE
            </button>
            <span className="text-[#33465e]">→</span>
            <span className="text-primary font-semibold bg-[#101b2c] px-2 py-0.5 rounded-sm border border-[#22354e]">
              05 REPORT
            </span>
          </div>
        </div>
      </div>

      {/* ======================================================== */}
      {/* 2. MAIN REPORT BODY                                      */}
      {/* ======================================================== */}
      <div className="flex-1 px-4 sm:px-6 lg:px-8 py-5 space-y-5 max-w-[1600px] w-full mx-auto">
        
        {/* COMPACT SUMMARY METRICS */}
        <div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {/* 1. Total Detections */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-1">
              <span className="font-mono text-[10px] text-[#8ea4bf] uppercase tracking-wider block">
                TOTAL DETECTIONS
              </span>
              <div className="text-2xl sm:text-3xl font-headline font-semibold text-on-surface">
                {analysisResult?.summary?.total_detections ?? summary.totalDetections}
              </div>
              <span className="font-mono text-[10px] text-[#64748b] block">
                Acoustic anomalies logged
              </span>
            </div>

            {/* 2. High Priority */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-1">
              <span className="font-mono text-[10px] text-[#8ea4bf] uppercase tracking-wider block">
                HIGH PRIORITY
              </span>
              <div className="text-2xl sm:text-3xl font-headline font-semibold text-primary">
                {analysisResult?.summary?.high_priority ?? summary.highPriority}
              </div>
              <span className="font-mono text-[10px] text-[#64748b] block">
                Requires operator review
              </span>
            </div>

            {/* 3. Requires Review */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-1">
              <span className="font-mono text-[10px] text-[#8ea4bf] uppercase tracking-wider block">
                REVIEW STATUS
              </span>
              <div className="text-2xl sm:text-3xl font-headline font-semibold text-amber-400">
                {summary.requiresReview} PENDING
              </div>
              <span className="font-mono text-[10px] text-[#64748b] block">
                Decision support queue
              </span>
            </div>

            {/* 4. Geolocation Status */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-1">
              <span className="font-mono text-[10px] text-[#8ea4bf] uppercase tracking-wider block">
                GEOLOCATION
              </span>
              <div className="text-lg sm:text-xl font-headline font-semibold text-amber-300 mt-1 flex items-center space-x-1.5">
                <span className="w-1.5 h-1.5 rounded-sm bg-amber-400"></span>
                <span>{analysisResult?.survey_metadata?.geolocation_available ? "AVAILABLE" : summary.geolocation}</span>
              </div>
              <span className="font-mono text-[10px] text-[#64748b] block">
                {analysisResult?.survey_metadata?.geolocation_available ? "EPSG:4326 · WGS 84" : "Image-space only · No GPS stream"}
              </span>
            </div>
          </div>

          <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-[#64748b] px-1">
            <span className="flex items-center space-x-1.5">
              <Info className="w-3 h-3 text-primary shrink-0" />
              <span>Deterministic decision-support intelligence. Review priority mapped from verified classes.</span>
            </span>
            <span className="hidden sm:inline">
              CRS: {analysisResult?.survey_metadata?.coordinate_system || 'EPSG:4326 (WGS 84)'}
            </span>
          </div>
        </div>

        {/* WORKSPACE GRID: MAIN REPORT TABLE + EVIDENCE & INTEGRITY PANEL */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          
          {/* ======================================================== */}
          {/* LEFT COLUMN: MAIN REPORT TABLE & ANALYST REVIEW (7/12)   */}
          {/* ======================================================== */}
          <div className="lg:col-span-7 space-y-4">
            
            {/* MAIN REPORT TABLE */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm overflow-hidden">
              <div className="p-3 bg-[#080d16] border-b border-[#162234] flex items-center justify-between font-mono">
                <div className="flex items-center space-x-2">
                  <FileCheck className="w-3.5 h-3.5 text-primary" />
                  <span className="text-xs font-semibold text-on-surface tracking-wider">
                    ANOMALY CLASSIFICATION REGISTER
                  </span>
                </div>
                <span className="text-[10px] text-[#64748b]">
                  {detections.length} DETECTIONS LOGGED
                </span>
              </div>

              {/* Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-xs">
                  <thead className="bg-[#05080e] text-[#8ea4bf] text-[10px] border-b border-[#162234] uppercase tracking-wider">
                    <tr>
                      <th className="py-2.5 px-3">ID</th>
                      <th className="py-2.5 px-3">CLASSIFICATION</th>
                      <th className="py-2.5 px-3">PRIORITY</th>
                      <th className="py-2.5 px-3">CONFIDENCE</th>
                      <th className="py-2.5 px-3">IMAGE POSITION</th>
                      <th className="py-2.5 px-3">GEOLOCATION</th>
                      <th className="py-2.5 px-3 text-right">STATUS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#162234]">
                    {detections.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-8 px-3 text-center text-[#64748b] font-mono text-xs">
                          No objects detected in this sonar swath.
                        </td>
                      </tr>
                    ) : (
                      detections.map((item) => {
                        const isSelected = item.detection_id === selectedId;
                      return (
                        <tr
                          key={item.detection_id}
                          onClick={() => handleSelectRow(item)}
                          className={`cursor-pointer transition-colors ${
                            isSelected
                              ? 'bg-[#101b2c] border-l-2 border-l-primary text-on-surface font-medium'
                              : 'hover:bg-[#0e1625] text-on-surface/90'
                          }`}
                        >
                          <td className="py-2.5 px-3">
                            <span className={`font-bold ${isSelected ? 'text-primary' : 'text-[#64748b]'}`}>
                              {item.detection_id}
                            </span>
                          </td>

                          <td className="py-2.5 px-3 font-semibold text-on-surface">
                            {item.classification}
                          </td>

                          <td className="py-2.5 px-3">
                            <span className={`px-1.5 py-0.2 rounded-sm text-[9px] font-bold border ${
                              item.priority === 'HIGH' ? 'bg-red-950/40 text-red-300 border-red-500/30' :
                              item.priority === 'MEDIUM' ? 'bg-amber-950/40 text-amber-300 border-amber-500/30' :
                              'bg-slate-800/40 text-slate-300 border-slate-600/30'
                            }`} title={item.priority_reason}>
                              {item.priority || 'LOW'}
                            </span>
                          </td>

                          <td className="py-2.5 px-3">
                            <span className={`px-1.5 py-0.2 rounded-sm text-[10px] font-bold border ${
                              item.confidence >= 0.85
                                ? 'bg-[#102a24] text-[#99f6e4] border-[#1b5e50]'
                                : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                            }`}>
                              {item.confidence_display}
                            </span>
                          </td>

                          <td className="py-2.5 px-3 text-[#8ea4bf]">
                            {item.image_position?.display}
                          </td>

                          <td className="py-2.5 px-3">
                            <span className="px-1.5 py-0.2 rounded-sm text-[9px] font-mono uppercase bg-amber-500/10 text-amber-400 border border-amber-500/30">
                              {item.geolocation_status}
                            </span>
                          </td>

                          <td className="py-2.5 px-3 text-right">
                            <span className="px-1.5 py-0.2 rounded-sm text-[9px] font-mono tracking-wider bg-[#080d16] border border-[#1b283d] text-[#8ea4bf]">
                              {item.status}
                            </span>
                          </td>
                        </tr>
                      );
                    }))}
                  </tbody>
                </table>
              </div>

              {/* Position Truth Note */}
              <div className="p-2.5 bg-[#05080e] border-t border-[#162234] flex items-center justify-between text-[10px] font-mono text-[#64748b]">
                <span>Coordinates: Image-space raster percentages only. Lat/Lon not invented.</span>
                <span className="text-primary/70">Click row to inspect evidence</span>
              </div>
            </div>

            {/* ANALYST REVIEW (Minimal Optional Field) */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <label 
                  htmlFor="analyst-notes-input"
                  className="font-mono text-xs uppercase tracking-wider text-on-surface font-semibold flex items-center space-x-1.5"
                >
                  <FileText className="w-3.5 h-3.5 text-primary" />
                  <span>ANALYST NOTES</span>
                </label>
                <span className="font-mono text-[10px] text-[#64748b]">
                  Optional operational notes · Included in exports
                </span>
              </div>
              <textarea
                id="analyst-notes-input"
                rows={3}
                value={analystNotes}
                onChange={(e) => setAnalystNotes(e.target.value)}
                placeholder="Add observations, review comments or operational notes..."
                className="w-full bg-[#070c14] border border-[#1a2638] focus:border-primary/60 rounded-sm p-2.5 text-xs font-mono text-on-surface placeholder:text-[#50637c] transition-colors resize-none outline-none"
              />
            </div>
          </div>

          {/* ======================================================== */}
          {/* RIGHT COLUMN: SELECTED DETECTION & REPORT INTEGRITY (5/12) */}
          {/* ======================================================== */}
          <div className="lg:col-span-5 space-y-4">
            
            {/* SELECTED DETECTION */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-3 font-mono">
              {!activeDetection ? (
                <div className="py-8 text-center space-y-2 font-mono">
                  <CheckCircle2 className="w-6 h-6 text-primary mx-auto opacity-75" />
                  <h3 className="text-xs font-bold text-on-surface uppercase">No Targets Detected</h3>
                  <p className="font-sans text-[11px] text-[#8ea4bf] max-w-xs mx-auto">
                    Clean acoustic survey swath. Zero anomalies flagged for reporting.
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between pb-2 border-b border-[#162234]">
                    <div>
                      <span className="text-[10px] text-primary uppercase font-bold tracking-wider block">
                        SELECTED DETECTION
                      </span>
                      <h3 className="text-base font-bold text-on-surface">
                        DETECTION #{activeDetection.detection_id}
                      </h3>
                    </div>
                    <span className="px-2 py-0.5 rounded-sm text-[10px] font-semibold bg-[#102a24] text-[#99f6e4] border border-[#1b5e50]">
                      {activeDetection.confidence_display} CONFIDENCE
                    </span>
                  </div>

                  {/* Key Attributes */}
                  <div className="divide-y divide-[#162234] text-xs space-y-1">
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Classification</span>
                      <span className="text-on-surface font-semibold">{activeDetection.classification}</span>
                    </div>
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Priority</span>
                      <span className={`px-1.5 py-0.2 rounded-sm text-[10px] font-bold border ${
                        activeDetection.priority === 'HIGH' ? 'bg-red-950/40 text-red-300 border-red-500/30' :
                        activeDetection.priority === 'MEDIUM' ? 'bg-amber-950/40 text-amber-300 border-amber-500/30' :
                        'bg-slate-800/40 text-slate-300 border-slate-600/30'
                      }`}>
                        {activeDetection.priority || 'LOW'}
                      </span>
                    </div>
                    {activeDetection.priority_reason && (
                      <div className="pt-1 pb-0.5 text-[10px] text-[#94a3b8] italic">
                        {activeDetection.priority_reason}
                      </div>
                    )}
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Confidence</span>
                      <span className="text-primary font-bold">{activeDetection.confidence_display}</span>
                    </div>
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Model Source</span>
                      <span className="text-on-surface font-mono text-[11px]">{activeDetection.model || activeDetection.source}</span>
                    </div>
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Review Status</span>
                      <span className="text-amber-300 font-semibold text-[11px]">{activeDetection.review_status || activeDetection.status}</span>
                    </div>
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Evidence Status</span>
                      <span className="text-primary font-semibold text-[11px]">{activeDetection.evidence_status || 'AVAILABLE'}</span>
                    </div>
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Image Position</span>
                      <span className="text-on-surface">{activeDetection.image_position?.display}</span>
                    </div>
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Geolocation</span>
                      <span className="text-amber-400 font-semibold">{activeDetection.geolocation_status}</span>
                    </div>
                    <div className="pt-1 flex justify-between items-center">
                      <span className="text-[#8ea4bf]">Navigation Metadata</span>
                      <span className="text-[#64748b]">{activeDetection.navigation_metadata}</span>
                    </div>
                  </div>

                  {/* Sonar Crop Thumbnail */}
                  <div className="pt-1">
                    <span className="text-[10px] uppercase text-[#8ea4bf] block mb-1">
                      EVIDENCE: CORRESPONDING SONAR CROP
                    </span>
                    
                    <div className="relative h-28 bg-[#02050a] border border-[#1a2638] rounded-sm overflow-hidden flex items-center justify-center">
                      <img
                        src={uploadedImageUrl || activeDetection.evidence_image}
                        alt={activeDetection.classification}
                        className="w-full h-full object-cover opacity-60 filter contrast-125 saturate-50"
                        onError={(e) => {
                          if (surveyFile && (surveyFile instanceof File || surveyFile instanceof Blob)) {
                            e.target.src = URL.createObjectURL(surveyFile);
                          } else {
                            e.target.style.display = 'none';
                          }
                        }}
                      />
                      
                      <div className="absolute inset-3 border border-primary/60 rounded-sm flex flex-col justify-between p-1.5 pointer-events-none">
                        <div className="flex justify-between items-center">
                          <span className="text-[8px] bg-[#030814]/90 px-1 rounded-sm text-primary">
                            ROI #{activeDetection.detection_id}
                          </span>
                          <Crosshair className="w-3 h-3 text-primary" />
                        </div>
                        <span className="text-[8px] text-[#8ea4bf] bg-[#030814]/80 px-1 rounded-sm self-start">
                          {activeDetection.image_position?.display}
                        </span>
                      </div>
                    </div>

                    <p className="mt-1.5 text-[10px] text-[#8ea4bf] line-clamp-2">
                      {activeDetection.acoustic_feature}
                    </p>
                  </div>

                  <button
                    onClick={() => {
                      soundFx.playTargetLock();
                      if (onNavigate) {
                        onNavigate('view-workspace');
                      }
                    }}
                    className="w-full py-2 px-3 rounded-sm bg-[#132338] hover:bg-[#1a2f4a] border border-[#273d5c] hover:border-primary/60 text-[#f1f5f9] text-xs flex items-center justify-center space-x-2 transition-colors cursor-pointer"
                  >
                    <span>VIEW IN EVIDENCE</span>
                    <ArrowRight className="w-3.5 h-3.5 text-primary" />
                  </button>
                </>
              )}
            </div>

            {/* REPORT INTEGRITY */}
            <div className="bg-[#0b111e] border border-[#1a2638] rounded-sm p-4 space-y-2.5 font-mono">
              <div className="flex items-center justify-between pb-2 border-b border-[#162234]">
                <span className="text-xs font-semibold text-on-surface uppercase tracking-wider flex items-center space-x-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-primary" />
                  <span>REPORT READINESS</span>
                </span>
                <span className="text-[9px] text-[#64748b]">INTEGRITY AUDIT</span>
              </div>

              <div className="space-y-1 text-xs">
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[#8ea4bf]">DETECTIONS</span>
                  <span className="text-primary font-bold">● {REPORT_READINESS_SPEC.detections}</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[#8ea4bf]">CLASSIFICATION</span>
                  <span className="text-primary font-bold">● {REPORT_READINESS_SPEC.classification}</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[#8ea4bf]">CONFIDENCE</span>
                  <span className="text-primary font-bold">● {REPORT_READINESS_SPEC.confidence}</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[#8ea4bf]">IMAGE EVIDENCE</span>
                  <span className="text-primary font-bold">● {REPORT_READINESS_SPEC.image_evidence}</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[#8ea4bf]">GEOLOCATION</span>
                  <span className="text-amber-400 font-bold">● {REPORT_READINESS_SPEC.geolocation}</span>
                </div>
              </div>

              <div className="mt-2 p-2 rounded-sm bg-[#070c14] border border-[#22354e] text-center">
                <span className="text-[9px] text-[#64748b] block uppercase tracking-wider">
                  STATUS:
                </span>
                <span className="text-xs font-bold text-primary tracking-widest block mt-0.5">
                  {REPORT_READINESS_SPEC.status}
                </span>
              </div>

              <p className="text-[10px] text-[#64748b] leading-relaxed">
                Model detections require human validation before operational sign-off. Report is flagged ready for review.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ======================================================== */}
      {/* 3. FINAL STATUS & EXPORT SUITE (Completion State)        */}
      {/* ======================================================== */}
      <div className="relative z-30 px-4 sm:px-6 lg:px-8 py-3 border-t border-[#162234] bg-[#070b14]/98 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5">
          <div className="w-6 h-6 rounded-sm bg-[#102a24] border border-[#1b5e50] flex items-center justify-center text-primary shrink-0">
            <CheckCircle2 className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="flex items-center space-x-2 font-mono text-xs">
              <span className="font-bold text-primary uppercase tracking-wider">
                REPORT READY
              </span>
              <span className="text-[#33465e]">·</span>
              <span className="text-[#64748b]">Stage 05 Completed</span>
            </div>
            <p className="text-xs text-[#8ea4bf]">
              Detection results and available evidence are ready for review and export.
            </p>
          </div>
        </div>

        {/* Action Export Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            id="btn-export-json"
            onClick={handleExportJSON}
            className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-sm bg-[#132338] hover:bg-[#1a2f4a] border border-[#273d5c] hover:border-primary/60 text-[#f1f5f9] font-mono text-xs font-semibold transition-colors cursor-pointer"
            title="Download structured JSON report with image-space detections"
          >
            <Download className="w-3.5 h-3.5 text-primary" />
            <span>EXPORT JSON</span>
          </button>

          <button
            id="btn-export-csv"
            onClick={handleExportCSV}
            className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-sm bg-[#0b111e] hover:bg-[#101826] border border-[#1b283d] hover:border-[#2a3c56] text-[#8ea4bf] hover:text-on-surface font-mono text-xs font-semibold transition-colors cursor-pointer"
            title="Download tabular CSV anomaly ledger"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-secondary" />
            <span>EXPORT CSV</span>
          </button>

          <button
            id="btn-generate-pdf"
            onClick={handleGeneratePDF}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-sm bg-[#0b111e] hover:bg-[#101826] border border-[#1b283d] hover:border-[#2a3c56] text-[#8ea4bf] hover:text-on-surface font-mono text-xs transition-colors cursor-pointer"
            title="Print official PDF survey dossier"
          >
            <Printer className="w-3.5 h-3.5 text-[#64748b]" />
            <span>GENERATE PDF</span>
          </button>
        </div>
      </div>
    </section>
  );
}
