import React, { useState, useEffect, useCallback } from 'react';
import TopAppBar from './components/TopAppBar';
import ExploreLanding from './components/views/ExploreLanding';
import WorkspaceView from './components/views/WorkspaceView';
import DetectionsView from './components/views/DetectionsView';
import ReportView from './components/views/ReportView';
import SensorTunerModal from './components/modals/SensorTunerModal';
import DispersalSimulationModal from './components/modals/DispersalSimulationModal';
import LegalModal from './components/modals/LegalModal';
import { soundFx } from './utils/audio';
import { SonarHero } from './components/SonarHero';
import SonarIngestView from './components/views/SonarIngestView';
import SonarQualityView from './components/views/SonarQualityView';
import BatchTriageView from './components/views/BatchTriageView';
import { 
  analyzeSonarImage, 
  analyzeBatchSonarImages, 
  getAnalyses, 
  getAnalysisById, 
  mapBackendDetection, 
  checkBackendHealth, 
  API_BASE_URL 
} from './services/api';

export default function App() {
  const [currentView, setCurrentView] = useState('view-hero');
  const [importedSurveyFile, setImportedSurveyFile] = useState(null);
  const [surveyMetadata, setSurveyMetadata] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [selectedAnomalyId, setSelectedAnomalyId] = useState(null);

  // Batch Screening State
  const [batchResults, setBatchResults] = useState(null);
  const [isBatchScanning, setIsBatchScanning] = useState(false);
  const [batchScanProgress, setBatchScanProgress] = useState(null);

  // Backend Integration State
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState(null);
  const [recentSurveys, setRecentSurveys] = useState([]);
  const [backendHealth, setBackendHealth] = useState({ connected: false, loading: true, status: 'checking' });

  // Modals & Drawers
  const [isSensorTunerOpen, setIsSensorTunerOpen] = useState(false);
  const [dispersalTarget, setDispersalTarget] = useState(null);
  const [isLegalOpen, setIsLegalOpen] = useState(false);

  // Check and warm up backend status on mount
  useEffect(() => {
    let isMounted = true;
    let retryCount = 0;
    const maxRetries = 8;
    let timerId = null;

    const probeBackend = async () => {
      try {
        const res = await checkBackendHealth();
        if (!isMounted) return;
        const isHealthy = res.status === 'healthy' || res.status === 'ok';
        setBackendHealth({
          connected: isHealthy,
          loading: false,
          status: isHealthy ? 'healthy' : 'degraded',
          data: res
        });
      } catch (err) {
        if (!isMounted) return;
        if (retryCount < maxRetries) {
          retryCount += 1;
          setBackendHealth({
            connected: false,
            loading: true,
            status: 'waking',
            retry: retryCount,
            error: err.message
          });
          timerId = setTimeout(probeBackend, 5000);
        } else {
          setBackendHealth({
            connected: false,
            loading: false,
            status: 'offline',
            error: err.message
          });
        }
      }
    };

    probeBackend();
    return () => {
      isMounted = false;
      if (timerId) clearTimeout(timerId);
    };
  }, []);

  // Fetch real past survey analyses from backend on mount
  useEffect(() => {
    let isMounted = true;
    getAnalyses({ page_size: 10 })
      .then((data) => {
        if (!isMounted || !data?.items) return;
        const formatted = data.items.map((item) => ({
          name: item.image?.filename || item.analysis_id,
          analysisId: item.analysis_id,
          size: item.image?.size_bytes ? `${Math.round(item.image.size_bytes / 1024)} KB` : 'N/A',
          timestamp: item.created_at || new Date().toISOString(),
          status: (item.status || 'COMPLETED').toUpperCase(),
          detectionsCount: item.summary?.total_detections ?? 0
        }));
        setRecentSurveys(formatted);
      })
      .catch((err) => {
        console.warn('Initial recent surveys load:', err);
      });
    return () => { isMounted = false; };
  }, []);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

      if (e.key === '1') {
        soundFx.playSonarPing(1100, 0.4);
        setCurrentView('view-landing');
      } else if (e.key === '2') {
        soundFx.playSonarPing(1200, 0.4);
        setCurrentView('view-workspace');
      } else if (e.key === '3') {
        soundFx.playSonarPing(1300, 0.4);
        setCurrentView('view-detections');
      } else if (e.key === '4') {
        soundFx.playSonarPing(1400, 0.4);
        setCurrentView('view-summary');
      } else if (e.key.toLowerCase() === 'm') {
        soundFx.toggleMute();
      } else if (e.key === 'Escape') {
        setIsSensorTunerOpen(false);
        setDispersalTarget(null);
        setIsLegalOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Execute Real Backend AI Analysis on an Uploaded File
  const handleRunAnalysis = useCallback(async (file, options = {}) => {
    const targetFile = file || importedSurveyFile;
    if (!targetFile) return null;

    const mergedOptions = {
      ...(surveyMetadata || {}),
      ...options
    };

    setIsAnalyzing(true);
    setAnalysisError(null);
    soundFx.playSonarPing(1350, 0.5);

    try {
      const result = await analyzeSonarImage(targetFile, mergedOptions);
      setAnalysisResult(result);

      // Map backend detections to frontend schema
      const mapped = (result.detections || []).map((d, idx) =>
        mapBackendDetection(d, idx, result.analysis_id)
      );

      setAnomalies(mapped);
      if (mapped.length > 0) {
        setSelectedAnomalyId(mapped[0].id);
      } else {
        setSelectedAnomalyId(null);
      }

      // Prepend newly persisted survey to recent session log
      setRecentSurveys((prev) => [
        {
          name: result.image?.filename || targetFile.name,
          analysisId: result.analysis_id,
          size: result.image?.size_bytes ? `${Math.round(result.image.size_bytes / 1024)} KB` : 'N/A',
          timestamp: new Date().toISOString(),
          status: 'COMPLETED',
          detectionsCount: result.summary?.total_detections ?? 0
        },
        ...prev.slice(0, 9)
      ]);

      soundFx.playTargetLock();
      return result;
    } catch (err) {
      console.warn('Analysis execution error:', err);
      const userMsg = err.userFriendlyMessage || err.message || 'Sonar analysis failed.';
      setAnalysisError(userMsg);
      setAnomalies([]);
      setSelectedAnomalyId(null);
      setAnalysisResult(null);
      soundFx.playSonarPing(700, 0.4);
      throw err;
    } finally {
      setIsAnalyzing(false);
    }
  }, [importedSurveyFile, surveyMetadata]);

  // Transition from Quality check to Detection view and trigger inference
  const handleProceedFromQuality = async () => {
    if (!importedSurveyFile) {
      setCurrentView('view-detections');
      return;
    }

    try {
      await handleRunAnalysis(importedSurveyFile, surveyMetadata);
      // ONLY navigate to results view if inference succeeded
      setCurrentView('view-detections');
    } catch (err) {
      // If validation fails (e.g. HTTP 422 Invalid Sonar Image),
      // DO NOT navigate to the results view as if analysis succeeded.
      // Navigate back to ingest view with error banner visible so user can select another image.
      setCurrentView('view-ingest');
    }
  };

  // Open an existing analysis from session history / backend persistence
  const handleOpenAnalysis = useCallback(async (analysisId) => {
    if (!analysisId) return;
    try {
      soundFx.playSonarPing(1300, 0.4);
      const record = await getAnalysisById(analysisId);
      if (!record) return;

      setAnalysisResult(record);
      const mapped = (record.detections || []).map((d, idx) =>
        mapBackendDetection(d, idx, record.analysis_id)
      );
      setAnomalies(mapped);
      if (mapped.length > 0) {
        setSelectedAnomalyId(mapped[0].id);
      } else {
        setSelectedAnomalyId(null);
      }

      setImportedSurveyFile({
        name: record.image?.filename || record.analysis_id,
        size: record.image?.size_bytes || 0,
        type: record.image?.content_type || 'image/jpeg',
        latitude: record.metadata?.latitude ?? null,
        longitude: record.metadata?.longitude ?? null,
        depth: record.metadata?.depth ?? null,
        heading: record.metadata?.heading ?? null,
        hasNavigation: Boolean(record.metadata?.geolocation_available)
      });

      soundFx.playTargetLock();
      setCurrentView('view-workspace');
    } catch (err) {
      console.warn('Failed to load past analysis:', err);
    }
  }, []);

  // Update Anomaly attribute (e.g. status or operator reclassification)
  const handleUpdateAnomaly = useCallback((anomalyId, updates) => {
    setAnomalies(prev => prev.map(a => {
      if (a.id === anomalyId) {
        return { ...a, ...updates };
      }
      return a;
    }));
  }, []);

  // Batch Anomaly Screening Handler
  const handleStartBatchScreening = useCallback(async (files, options = {}) => {
    soundFx.playTargetLock();
    // Sort files in natural numerical order (e.g. 01, 02, ... 15) so progress is strictly sequential
    const sortedFiles = [...(files || [])].sort((a, b) =>
      (a.name || '').localeCompare(b.name || '', undefined, { numeric: true, sensitivity: 'base' })
    );

    setIsBatchScanning(true);
    setBatchScanProgress({
      currentIndex: 0,
      total: sortedFiles.length,
      progress: 0,
      filename: sortedFiles[0]?.name || '',
      flaggedCount: 0,
      cleanCount: 0
    });
    setCurrentView('view-batch-triage');

    try {
      const results = await analyzeBatchSonarImages(sortedFiles, options, (progress) => {
        setBatchScanProgress(progress);
      });
      setBatchResults(results);
      soundFx.playTargetLock();

      if (results.all && results.all.length > 0) {
        setRecentSurveys((prev) => [
          ...results.all.map((item) => ({
            name: item.filename,
            analysisId: item.analysisId,
            size: item.size ? `${Math.round(item.size / 1024)} KB` : 'N/A',
            timestamp: new Date().toISOString(),
            status: item.hasAnomalies ? 'FLAGGED' : 'CLEAN',
            detectionsCount: item.detectionsCount || 0
          })),
          ...prev.slice(0, 10)
        ]);
      }
    } catch (err) {
      console.warn('Batch screening error:', err);
      setAnalysisError(err.userFriendlyMessage || err.message || 'Batch screening failed.');
    } finally {
      setIsBatchScanning(false);
    }
  }, []);

  // Inspect specific item from batch triage
  const handleInspectBatchItem = useCallback((batchItem) => {
    soundFx.playTargetLock();
    setImportedSurveyFile(batchItem.file);
    setAnalysisResult(batchItem.rawResult);
    setAnomalies(batchItem.detections || []);
    if (batchItem.detections && batchItem.detections.length > 0) {
      setSelectedAnomalyId(batchItem.detections[0].id);
    } else {
      setSelectedAnomalyId(null);
    }
    setCurrentView('view-workspace');
  }, []);

  // Update Anomaly Status from Operator in Detections view
  const handleUpdateAnomalyStatus = (id, newStatus, operatorNotes) => {
    setAnomalies(prev => prev.map(item => {
      if (item.id === id) {
        return {
          ...item,
          status: newStatus,
          notes: operatorNotes || item.notes,
          reviewedBy: "Operator (Verified)",
          reviewedAt: new Date().toISOString()
        };
      }
      return item;
    }));
  };

  return (
    <div className="h-screen w-screen bg-[#060911] text-[#f1f5f9] overflow-hidden flex flex-col font-sans">
      {/* Top Application Bar */}
      <TopAppBar
        currentView={currentView}
        onSwitchView={setCurrentView}
        onOpenSensorTuner={() => setIsSensorTunerOpen(true)}
        anomalyCount={anomalies.filter(a => a.status === 'REQUIRES REVIEW' || a.status === 'PENDING REVIEW').length}
        surveyFile={importedSurveyFile}
        onOpenLegal={() => setIsLegalOpen(true)}
        backendHealth={backendHealth}
        batchCount={batchResults?.flaggedCount}
      />

      {/* Main View Container */}
      <main className="relative flex-1 mt-14 overflow-hidden">
        {currentView === 'view-hero' && (
          <div className="animate-fade-in h-full">
            <SonarHero
              onExplore={() => {
                setCurrentView('view-ingest');
              }}
              onStartAnalysis={() => {
                setCurrentView('view-ingest');
              }}
              onViewDetections={() => {
                setCurrentView('view-detections');
              }}
            />
          </div>
        )}

        {currentView === 'view-ingest' && (
          <div className="animate-fade-in h-full">
            <SonarIngestView
              onNavigate={setCurrentView}
              recentSurveys={recentSurveys}
              analysisError={analysisError}
              onClearError={() => setAnalysisError(null)}
              onOpenAnalysis={handleOpenAnalysis}
              onStartBatchScreening={handleStartBatchScreening}
              onContinueToQualityCheck={(file, metadata) => {
                setImportedSurveyFile(file);
                if (metadata) setSurveyMetadata(metadata);
                setAnalysisError(null);
                setAnomalies([]);
                setSelectedAnomalyId(null);
                setAnalysisResult(null);
                setCurrentView('view-quality');
              }}
            />
          </div>
        )}

        {currentView === 'view-batch-triage' && (
          <div className="animate-fade-in h-full">
            <BatchTriageView
              batchResults={batchResults}
              isScanning={isBatchScanning}
              scanProgress={batchScanProgress}
              onInspectImage={handleInspectBatchItem}
              onNewBatchScan={() => setCurrentView('view-ingest')}
              onNavigate={setCurrentView}
            />
          </div>
        )}

        {currentView === 'view-quality' && (
          <div className="animate-fade-in h-full">
            <SonarQualityView
              surveyFile={importedSurveyFile}
              onNavigate={setCurrentView}
              onContinueToDetection={handleProceedFromQuality}
              isAnalyzing={isAnalyzing}
            />
          </div>
        )}

        {currentView === 'view-landing' && (
          <div className="animate-fade-in h-full">
            <ExploreLanding
              anomalies={anomalies}
              onNavigate={setCurrentView}
              onSelectAnomaly={setSelectedAnomalyId}
            />
          </div>
        )}

        {currentView === 'view-workspace' && (
          <div className="animate-fade-in h-full">
            <WorkspaceView
              anomalies={anomalies}
              selectedAnomalyId={selectedAnomalyId}
              onSelectAnomaly={setSelectedAnomalyId}
              onNavigate={setCurrentView}
              surveyFile={importedSurveyFile}
              analysisResult={analysisResult}
              onUpdateAnomaly={handleUpdateAnomaly}
            />
          </div>
        )}

        {currentView === 'view-detections' && (
          <div className="animate-fade-in h-full">
            <DetectionsView
              anomalies={anomalies}
              selectedAnomalyId={selectedAnomalyId}
              onSelectAnomaly={setSelectedAnomalyId}
              onUpdateAnomalyStatus={handleUpdateAnomaly}
              onUpdateAnomaly={handleUpdateAnomaly}
              onNavigate={setCurrentView}
              surveyFile={importedSurveyFile}
              analysisResult={analysisResult}
              isAnalyzing={isAnalyzing}
              analysisError={analysisError}
              onRunAnalysis={handleRunAnalysis}
              evidenceUrl={analysisResult?.evidence_url ? (analysisResult.evidence_url.startsWith('http') ? analysisResult.evidence_url : `${API_BASE_URL}${analysisResult.evidence_url}`) : null}
            />
          </div>
        )}

        {currentView === 'view-summary' && (
          <div className="animate-fade-in h-full">
            <ReportView
              anomalies={anomalies}
              onSelectAnomaly={setSelectedAnomalyId}
              onNavigate={setCurrentView}
              surveyFile={importedSurveyFile}
              analysisResult={analysisResult}
            />
          </div>
        )}
      </main>

      {/* Modals */}
      <SensorTunerModal
        isOpen={isSensorTunerOpen}
        onClose={() => setIsSensorTunerOpen(false)}
      />

      <DispersalSimulationModal
        isOpen={!!dispersalTarget}
        anomaly={dispersalTarget}
        onClose={() => setDispersalTarget(null)}
      />

      <LegalModal
        isOpen={isLegalOpen}
        onClose={() => setIsLegalOpen(false)}
      />
    </div>
  );
}

