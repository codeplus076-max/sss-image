import React, { useState } from 'react';
import { 
  AlertTriangle, 
  CheckCircle2, 
  Scan, 
  Download, 
  ExternalLink, 
  Eye, 
  Filter, 
  Layers, 
  ShieldAlert, 
  ArrowRight, 
  RefreshCw, 
  FileText, 
  Sparkles,
  ChevronRight,
  ShieldCheck,
  Search,
  Database,
  XCircle
} from 'lucide-react';
import { soundFx } from '../../utils/audio';

export default function BatchTriageView({
  batchResults,
  isScanning,
  scanProgress,
  onInspectImage,
  onNewBatchScan,
  onCancelScan,
  onNavigate
}) {
  const [activeTab, setActiveTab] = useState('flagged'); // 'flagged' | 'clean' | 'failed' | 'all'
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  const flaggedList = batchResults?.flagged || [];
  const cleanList = batchResults?.clean || [];
  const failedList = batchResults?.failed || [];
  const allList = batchResults?.all || [];
  const totalScanned = batchResults?.totalScanned || allList.length || 0;

  // Extract all unique anomaly categories across the flagged images
  const allCategories = ['ALL', ...Array.from(new Set(
    flaggedList.flatMap(item => item.categories || [])
  ))];

  // Filter items according to active tab and category/search
  const getDisplayedItems = () => {
    let baseList = [];
    if (activeTab === 'flagged') baseList = flaggedList;
    else if (activeTab === 'clean') baseList = cleanList;
    else if (activeTab === 'failed') baseList = failedList;
    else baseList = allList;

    return baseList.filter(item => {
      // Category filter (only relevant for flagged/all)
      if (selectedCategory !== 'ALL') {
        const matchesCategory = item.categories?.some(c => c.toLowerCase() === selectedCategory.toLowerCase());
        if (!matchesCategory) return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = item.filename?.toLowerCase().includes(query);
        const matchesCat = item.categories?.some(c => c.toLowerCase().includes(query));
        if (!matchesName && !matchesCat) return false;
      }

      return true;
    });
  };

  const displayedItems = getDisplayedItems();

  // Export anomaly summary as JSON
  const handleExportJSON = () => {
    soundFx.playTargetLock();
    const payload = {
      export_type: "SONAROPS_BATCH_ANOMALY_TRIAGE",
      timestamp: new Date().toISOString(),
      summary: {
        total_scanned: totalScanned,
        flagged_with_anomalies: flaggedList.length,
        clean_seabed_tiles: cleanList.length,
      },
      flagged_surveys: flaggedList.map(item => ({
        filename: item.filename,
        analysis_id: item.analysisId,
        detections_count: item.detectionsCount,
        highest_confidence: item.highestConfidence,
        detected_categories: item.categories,
        detections: (item.detections || []).map(d => ({
          label: d.semantic_class_name || d.name,
          confidence: d.confidence,
          box: d.bounding_box || d.box,
        }))
      }))
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sonar_anomaly_batch_report_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export anomaly summary as CSV
  const handleExportCSV = () => {
    soundFx.playTargetLock();
    const headers = ['Filename', 'Analysis ID', 'Anomalies Count', 'Highest Confidence', 'Target Classes'];
    const rows = flaggedList.map(item => [
      `"${item.filename}"`,
      `"${item.analysisId || 'N/A'}"`,
      item.detectionsCount,
      `${(item.highestConfidence * 100).toFixed(1)}%`,
      `"${(item.categories || []).join(', ')}"`
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `sonar_flagged_anomalies_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="relative w-full h-[calc(100vh-3.5rem)] overflow-y-auto bg-[#060911] text-[#f1f5f9] select-none p-4 sm:p-6 lg:p-8">
      <div className="max-w-7xl mx-auto space-y-6 pb-12">
        
        {/* ======================================================== */}
        {/* 1. HEADER & BATCH METRICS BANNER                         */}
        {/* ======================================================== */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/[0.06] pb-6">
          <div>
            <div className="flex items-center space-x-2 text-xs font-mono text-primary mb-1">
              <Scan className="w-4 h-4 animate-pulse" />
              <span className="tracking-wider uppercase font-semibold">Autonomous Acoustic Triage Hub</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-serif text-[#f8fafc] tracking-tight">
              Batch Anomaly Screening
            </h1>
            <p className="text-xs sm:text-sm text-[#8ea4bf] max-w-2xl mt-1">
              Multi-swath AI triage: separating high-priority bottom contacts and anomalies from clear seabed swaths.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            {isScanning && (
              <button
                onClick={() => {
                  soundFx.playWarning();
                  onCancelScan?.();
                }}
                className="flex items-center space-x-2 px-3.5 py-2 rounded-sm bg-red-950/40 hover:bg-red-900/60 border border-red-500/40 text-xs font-mono text-red-300 hover:text-white transition-colors cursor-pointer"
                title="Immediately halt active batch scanning"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>Cancel Scan</span>
              </button>
            )}
            <button
              onClick={onNewBatchScan}
              className="flex items-center space-x-2 px-3.5 py-2 rounded-sm bg-[#0c1424] hover:bg-[#132038] border border-white/[0.1] text-xs font-mono text-[#cbd5e1] hover:text-white transition-colors cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Scan New Batch</span>
            </button>
            <button
              onClick={handleExportJSON}
              disabled={flaggedList.length === 0}
              className={`flex items-center space-x-2 px-4 py-2 rounded-sm text-xs font-mono font-medium transition-all ${
                flaggedList.length > 0 
                  ? 'bg-primary text-[#060911] hover:bg-primary/90 shadow-[0_0_12px_rgba(45,212,191,0.3)] cursor-pointer'
                  : 'bg-white/[0.05] text-[#64748b] border border-white/[0.05] cursor-not-allowed'
              }`}
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Flagged Anomalies</span>
            </button>
          </div>
        </div>

        {/* ======================================================== */}
        {/* 2. REAL-TIME PROGRESS BAR (WHEN BATCH SCAN IS ACTIVE)    */}
        {/* ======================================================== */}
        {isScanning && (
          <div className="p-4 sm:p-5 rounded-sm bg-[#09111e] border border-primary/30 shadow-[0_0_24px_rgba(45,212,191,0.15)] space-y-3">
            <div className="flex items-center justify-between text-xs font-mono">
              <div className="flex items-center space-x-2 text-primary">
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span className="font-semibold uppercase tracking-wider">
                  Screening File {scanProgress?.currentIndex || 1} of {scanProgress?.total || 1}...
                </span>
                <span className="text-[#94a3b8] italic hidden sm:inline">
                  ({scanProgress?.filename})
                </span>
              </div>
              <div className="flex items-center space-x-3">
                <span className="text-primary font-bold">{scanProgress?.progress || 0}%</span>
                <button
                  onClick={() => {
                    soundFx.playWarning();
                    onCancelScan?.();
                  }}
                  className="px-2.5 py-0.5 rounded text-[11px] font-mono uppercase bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30 transition-colors cursor-pointer"
                  title="Stop scan immediately"
                >
                  Stop
                </button>
              </div>
            </div>

            <div className="w-full bg-[#131d2e] h-2 rounded-full overflow-hidden">
              <div 
                className="bg-primary h-full transition-all duration-300 rounded-full shadow-[0_0_8px_rgba(45,212,191,0.6)]"
                style={{ width: `${scanProgress?.progress || 0}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-[#64748b]">
              <span>Models: Multi-model ONNX accelerated pipeline</span>
              <div className="flex items-center space-x-4">
                <span className="text-amber-400">⚡ {scanProgress?.flaggedCount || 0} Anomalies Detected</span>
                <span className="text-emerald-400">✓ {scanProgress?.cleanCount || 0} Clean Seabed</span>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* 3. BATCH TRIAGE METRICS CARDS                            */}
        {/* ======================================================== */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 font-mono">
          {/* Card 1: Flagged */}
          <div 
            onClick={() => { setActiveTab('flagged'); soundFx.playSonarPing(1200, 0.3); }}
            className={`p-4 rounded-sm border transition-all cursor-pointer ${
              activeTab === 'flagged'
                ? 'bg-red-950/20 border-red-500/60 shadow-[0_0_16px_rgba(239,68,68,0.15)]'
                : 'bg-[#09111e]/70 border-white/[0.08] hover:border-red-500/30'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#94a3b8] uppercase tracking-wider">Abnormalities Flagged</span>
              <ShieldAlert className="w-4 h-4 text-red-400" />
            </div>
            <div className="text-3xl font-bold text-red-300 mt-2">
              {flaggedList.length}
            </div>
            <div className="text-[11px] text-red-400/80 mt-1 flex items-center space-x-1">
              <span>●</span>
              <span>Images with confirmed contacts</span>
            </div>
          </div>

          {/* Card 2: Clean Seabed */}
          <div 
            onClick={() => { setActiveTab('clean'); soundFx.playSonarPing(1100, 0.3); }}
            className={`p-4 rounded-sm border transition-all cursor-pointer ${
              activeTab === 'clean'
                ? 'bg-emerald-950/20 border-emerald-500/60 shadow-[0_0_16px_rgba(16,185,129,0.15)]'
                : 'bg-[#09111e]/70 border-white/[0.08] hover:border-emerald-500/30'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#94a3b8] uppercase tracking-wider">Clean / Clear Seabed</span>
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-3xl font-bold text-emerald-300 mt-2">
              {cleanList.length}
            </div>
            <div className="text-[11px] text-emerald-400/80 mt-1 flex items-center space-x-1">
              <span>●</span>
              <span>Zero contact signatures verified</span>
            </div>
          </div>

          {/* Card 3: Total Survey Batch */}
          <div 
            onClick={() => { setActiveTab('all'); soundFx.playSonarPing(1000, 0.3); }}
            className={`p-4 rounded-sm border transition-all cursor-pointer ${
              activeTab === 'all'
                ? 'bg-primary/10 border-primary/60 shadow-[0_0_16px_rgba(45,212,191,0.15)]'
                : 'bg-[#09111e]/70 border-white/[0.08] hover:border-primary/30'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#94a3b8] uppercase tracking-wider">Total Scanned Files</span>
              <Layers className="w-4 h-4 text-primary" />
            </div>
            <div className="text-3xl font-bold text-primary mt-2">
              {totalScanned}
            </div>
            <div className="text-[11px] text-[#8ea4bf] mt-1 flex items-center space-x-1">
              <span>●</span>
              <span>{(flaggedList.length / Math.max(1, totalScanned) * 100).toFixed(0)}% Anomaly detection rate</span>
            </div>
          </div>
        </div>

        {/* ======================================================== */}
        {/* 4. FILTER TABS & SEARCH BAR                              */}
        {/* ======================================================== */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
          {/* Main Filter Tabs */}
          <div className="flex items-center space-x-1 p-1 bg-[#09111e] border border-white/[0.08] rounded-sm text-xs font-mono">
            <button
              onClick={() => { setActiveTab('flagged'); soundFx.playSonarPing(1200, 0.3); }}
              className={`px-3 py-1.5 rounded-sm transition-colors cursor-pointer flex items-center space-x-1.5 ${
                activeTab === 'flagged'
                  ? 'bg-red-500/20 text-red-200 border border-red-500/40 font-semibold'
                  : 'text-[#8ea4bf] hover:text-white'
              }`}
            >
              <span>🚨 Abnormalities Detected</span>
              <span className="bg-red-500/30 text-red-200 px-1.5 py-0.2 rounded-xs text-[10px]">
                {flaggedList.length}
              </span>
            </button>

            <button
              onClick={() => { setActiveTab('clean'); soundFx.playSonarPing(1100, 0.3); }}
              className={`px-3 py-1.5 rounded-sm transition-colors cursor-pointer flex items-center space-x-1.5 ${
                activeTab === 'clean'
                  ? 'bg-emerald-500/20 text-emerald-200 border border-emerald-500/40 font-semibold'
                  : 'text-[#8ea4bf] hover:text-white'
              }`}
            >
              <span>🟢 Clean Seabed</span>
              <span className="bg-emerald-500/30 text-emerald-200 px-1.5 py-0.2 rounded-xs text-[10px]">
                {cleanList.length}
              </span>
            </button>

            <button
              onClick={() => { setActiveTab('all'); soundFx.playSonarPing(1000, 0.3); }}
              className={`px-3 py-1.5 rounded-sm transition-colors cursor-pointer flex items-center space-x-1.5 ${
                activeTab === 'all'
                  ? 'bg-primary/20 text-primary border border-primary/40 font-semibold'
                  : 'text-[#8ea4bf] hover:text-white'
              }`}
            >
              <span>All Scanned ({totalScanned})</span>
            </button>

            {failedList.length > 0 && (
              <button
                onClick={() => { setActiveTab('failed'); soundFx.playSonarPing(900, 0.3); }}
                className={`px-3 py-1.5 rounded-sm transition-colors cursor-pointer flex items-center space-x-1.5 ${
                  activeTab === 'failed'
                    ? 'bg-amber-500/20 text-amber-200 border border-amber-500/50 font-semibold'
                    : 'text-amber-400/80 hover:text-amber-200'
                }`}
              >
                <span>⚠️ Failed / Timeout ({failedList.length})</span>
              </button>
            )}
          </div>

          {/* Search by filename or target class */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter by filename or hazard..."
              className="pl-8 pr-3 py-1.5 bg-[#09111e] border border-white/[0.08] focus:border-primary/50 text-xs font-mono text-white placeholder-[#64748b] rounded-sm outline-none w-full sm:w-64"
            />
          </div>
        </div>

        {/* ======================================================== */}
        {/* 5. ANOMALY CARDS GRID (PRIMARY USER FOCUS)               */}
        {/* ======================================================== */}
        {displayedItems.length === 0 ? (
          <div className="p-12 text-center border border-dashed border-white/[0.1] rounded-sm bg-[#080e1a]/50 space-y-3 font-mono">
            <div className="w-12 h-12 mx-auto rounded-full bg-white/[0.03] flex items-center justify-center text-[#64748b]">
              <Search className="w-6 h-6" />
            </div>
            <div className="text-sm text-[#cbd5e1]">No sonar files match the current filter.</div>
            <div className="text-xs text-[#64748b]">
              {activeTab === 'flagged' 
                ? 'No abnormalities were detected in this filter selection.' 
                : 'Switch tabs or clear your search query.'}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
            {displayedItems.map((item, idx) => {
              const hasAnomalies = item.hasAnomalies;
              const detections = item.detections || [];
              const highestConf = (item.highestConfidence * 100).toFixed(1);

              return (
                <div
                  key={item.id || idx}
                  className={`flex flex-col justify-between rounded-sm border transition-all overflow-hidden ${
                    hasAnomalies
                      ? 'bg-[#09111e] border-amber-500/30 hover:border-amber-400 shadow-[0_4px_20px_rgba(0,0,0,0.5)]'
                      : 'bg-[#080d17] border-white/[0.07] hover:border-emerald-500/40 opacity-80 hover:opacity-100'
                  }`}
                >
                  {/* Top Thumbnail Preview with Bounding Box Overlays */}
                  <div className="relative w-full h-52 bg-[#02050b] overflow-hidden group flex items-center justify-center">
                    {item.previewUrl ? (
                      <div className="relative h-full flex items-center justify-center">
                        <img
                          src={item.previewUrl}
                          alt={item.filename}
                          className="h-full w-auto max-w-full object-contain filter contrast-125 block"
                        />
                        {/* Visual Overlay of Bounding Boxes directly mapped to the image element */}
                        {hasAnomalies && detections.map((det, dIdx) => {
                          const box = det.bounding_box || det.box || {};
                          const normX = box.norm_x1 != null ? box.norm_x1 * 100 : (box.x != null ? box.x : 0);
                          const normY = box.norm_y1 != null ? box.norm_y1 * 100 : (box.y != null ? box.y : 0);
                          const normW = box.norm_w != null ? box.norm_w * 100 : (box.w != null ? box.w : 10);
                          const normH = box.norm_h != null ? box.norm_h * 100 : (box.h != null ? box.h : 10);

                          return (
                            <div
                              key={dIdx}
                              style={{
                                left: `${Math.max(0, Math.min(96, normX))}%`,
                                top: `${Math.max(0, Math.min(96, normY))}%`,
                                width: `${Math.max(3, Math.min(100 - normX, normW))}%`,
                                height: `${Math.max(3, Math.min(100 - normY, normH))}%`,
                              }}
                              className="absolute border-2 border-cyan-400 bg-cyan-400/20 pointer-events-none shadow-[0_0_8px_rgba(45,212,191,0.8)]"
                            />
                          );
                        })}
                      </div>
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-xs font-mono text-[#64748b]">
                        <span>Acoustic Swath Preview</span>
                      </div>
                    )}

                    {/* Status Badge Tag */}
                    <div className="absolute top-2.5 left-2.5 font-mono text-[10px] px-2 py-0.5 rounded-xs flex items-center space-x-1.5 shadow-md">
                      {item.isError ? (
                        <span className="bg-amber-950/90 border border-amber-500/60 text-amber-200 px-2 py-0.5 rounded-xs flex items-center space-x-1">
                          <AlertTriangle className="w-3 h-3 text-amber-400" />
                          <span>TIMEOUT / RETRY</span>
                        </span>
                      ) : hasAnomalies ? (
                        <span className="bg-red-950/80 border border-red-500/50 text-red-200 px-2 py-0.5 rounded-xs flex items-center space-x-1">
                          <AlertTriangle className="w-3 h-3 text-red-400" />
                          <span>{item.detectionsCount} {item.detectionsCount === 1 ? 'ANOMALY' : 'ANOMALIES'}</span>
                        </span>
                      ) : item.isCleanTriage ? (
                        <span className="bg-emerald-950/80 border border-emerald-500/50 text-emerald-200 px-2 py-0.5 rounded-xs flex items-center space-x-1" title={`Natural Seabed Gate: ${((item.triage?.clean_prob || 0) * 100).toFixed(1)}% clean seabed confidence`}>
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          <span>CLEAN SEABED (TRIAGE BYPASS {((item.triage?.clean_prob || 0) * 100).toFixed(0)}%)</span>
                        </span>
                      ) : (
                        <span className="bg-emerald-950/80 border border-emerald-500/50 text-emerald-200 px-2 py-0.5 rounded-xs flex items-center space-x-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          <span>CLEAN SEABED (FULL SCAN)</span>
                        </span>
                      )}
                    </div>

                    {/* Confidence Rating Tag */}
                    {hasAnomalies && (
                      <div className="absolute top-2.5 right-2.5 bg-[#060911]/90 border border-white/[0.15] text-[10px] font-mono text-primary px-2 py-0.5 rounded-xs">
                        {highestConf}% CONF
                      </div>
                    )}
                  </div>

                  {/* Body Content */}
                  <div className="p-4 space-y-3 flex-1 flex flex-col justify-between">
                    <div>
                      {/* Filename & Analysis ID */}
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h3 
                            className="font-mono text-xs font-semibold text-white truncate" 
                            title={item.filename}
                          >
                            {item.filename}
                          </h3>
                          <div className="text-[10px] font-mono text-[#64748b]">
                            {item.analysisId || 'Survey Swath Tile'}
                          </div>
                        </div>
                      </div>

                      {/* Detected Classes Pills */}
                      {hasAnomalies && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {item.categories?.map((cat, cIdx) => (
                            <span 
                              key={cIdx}
                              className="text-[9px] font-mono px-2 py-0.5 rounded-xs bg-amber-500/10 border border-amber-500/30 text-amber-300 font-medium"
                            >
                              {cat}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Footer Action Button */}
                    <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between">
                      <div className="text-[10px] font-mono text-[#8ea4bf]">
                        {hasAnomalies ? (
                          <span className="text-amber-400">● Requires Operator Review</span>
                        ) : (
                          <span className="text-emerald-400">● Certified Clear</span>
                        )}
                      </div>

                      <button
                        onClick={() => {
                          soundFx.playTargetLock();
                          if (onInspectImage) onInspectImage(item);
                        }}
                        className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xs text-[11px] font-mono font-medium transition-all cursor-pointer ${
                          hasAnomalies
                            ? 'bg-primary text-[#060911] hover:bg-primary/90 shadow-[0_0_10px_rgba(45,212,191,0.25)]'
                            : 'bg-white/[0.05] text-[#94a3b8] hover:text-white hover:bg-white/[0.1] border border-white/[0.08]'
                        }`}
                      >
                        <Eye className="w-3 h-3" />
                        <span>{hasAnomalies ? 'Inspect Anomalies' : 'View Swath'}</span>
                        <ArrowRight className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

      </div>
    </div>
  );
}
