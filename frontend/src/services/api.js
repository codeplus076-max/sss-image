/**
 * SonarOps Marine Intelligence — Backend API Client
 * 
 * Centralized service for communicating with the FastAPI backend.
 * Base URL configurable via VITE_API_BASE_URL.
 */

export const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message, status, data = null, userFriendlyMessage = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.userFriendlyMessage = userFriendlyMessage || message;
  }
}

export class SonarValidationError extends ApiError {
  constructor(data) {
    const userMessage = data?.message || 'The uploaded image does not appear to be a valid Side-Scan Sonar image.';
    const details = data?.details || 'Please upload a valid Side-Scan Sonar survey image.';
    super(userMessage, 422, data, `Invalid sonar image. ${details}`);
    this.name = 'SonarValidationError';
    this.errorCode = data?.error || 'INVALID_SONAR_IMAGE';
  }
}

/**
 * Standard class label mappings per specification
 */
export const CLASS_LABEL_MAP = {
  'cylinder': 'Cylinder',
  'crab-pot': 'Ghost Gear / Crab-Pot',
  'ghost gear': 'Ghost Gear / Crab-Pot',
  'ghost gear / crab pot': 'Ghost Gear / Crab-Pot',
  'ghost gear / crab-pot': 'Ghost Gear / Crab-Pot',
  'pipeline': 'Subsea Pipeline',
  'subsea pipeline': 'Subsea Pipeline',
  'shipwreck': 'Shipwreck',
  'milco': 'Mine-Like Contact',
  'nombo': 'Non-Mine Mine-Like Bottom Object',
  'class_0': 'Class_0 (Unknown / Unlabeled)',
  'class_0 (unknown / unlabeled)': 'Class_0 (Unknown / Unlabeled)',
  'unknown / unlabeled artifact': 'Class_0 (Unknown / Unlabeled)'
};

/**
 * Maps raw backend detection to unified frontend detection item
 */
export function mapBackendDetection(rawDet, index = 0, analysisId = null) {
  const code = rawDet.code || String(index + 1).padStart(2, '0');
  const id = rawDet.id || `DET-${code}`;

  const rawClass = (rawDet.display_class || rawDet.raw_class || '').toLowerCase();
  const displayClass = CLASS_LABEL_MAP[rawClass] || rawDet.display_class || rawDet.raw_class || 'Acoustic Anomaly';
  const className = (rawDet.className || displayClass).toUpperCase();

  // Confidence percentage display [0 - 100%]
  let confidenceVal = 0;
  if (typeof rawDet.confidence_percent === 'number') {
    confidenceVal = rawDet.confidence_percent;
  } else if (typeof rawDet.confidence === 'number') {
    confidenceVal = rawDet.confidence <= 1.0 ? Math.round(rawDet.confidence * 1000) / 10 : rawDet.confidence;
  }

  // Extract normalized percentage box coordinates [0 - 100%] for pixel-perfect CSS overlays
  let bx = 0, by = 0, bw = 0, bh = 0;
  if (rawDet.bbox) {
    if (typeof rawDet.bbox.x === 'number' && typeof rawDet.bbox.w === 'number') {
      bx = rawDet.bbox.x;
      by = rawDet.bbox.y;
      bw = rawDet.bbox.w;
      bh = rawDet.bbox.h;
    } else if (typeof rawDet.bbox.norm_x1 === 'number') {
      bx = rawDet.bbox.norm_x1 * 100;
      by = rawDet.bbox.norm_y1 * 100;
      bw = (rawDet.bbox.norm_w ?? (rawDet.bbox.norm_x2 ? rawDet.bbox.norm_x2 - rawDet.bbox.norm_x1 : 0.1)) * 100;
      bh = (rawDet.bbox.norm_h ?? (rawDet.bbox.norm_y2 ? rawDet.bbox.norm_y2 - rawDet.bbox.norm_y1 : 0.1)) * 100;
    }
  }
  bx = Math.max(0, Math.min(100, bx));
  by = Math.max(0, Math.min(100, by));
  bw = Math.max(0, Math.min(100 - bx, bw));
  bh = Math.max(0, Math.min(100 - by, bh));

  const box = { x: bx, y: by, w: bw, h: bh };

  const hasGeo = rawDet.latitude != null && rawDet.longitude != null;
  const evidenceUrl = rawDet.evidenceImage 
    ? (rawDet.evidenceImage.startsWith('http') ? rawDet.evidenceImage : `${API_BASE_URL}${rawDet.evidenceImage}`)
    : (analysisId ? `${API_BASE_URL}/api/v1/analysis/${analysisId}/evidence` : null);

  return {
    id,
    code,
    class: className,
    className,
    display_class: displayClass,
    category: rawDet.category || displayClass,
    raw_class: rawDet.raw_class,
    type: rawDet.type || displayClass,
    confidence: confidenceVal,
    confidence_raw: rawDet.confidence,
    confidence_display: `${confidenceVal}%`,
    priority: rawDet.priority || rawDet.intelligence?.priority || 'LOW',
    priority_reason: rawDet.priority_reason || rawDet.intelligence?.priority_reason || 'Requires contextual operator review.',
    review_status: rawDet.review_status || rawDet.status || 'PENDING REVIEW',
    evidence_status: rawDet.evidence_status || rawDet.intelligence?.evidence_status || 'AVAILABLE',
    intelligence: rawDet.intelligence || {
      priority: rawDet.priority || 'LOW',
      priority_reason: rawDet.priority_reason || 'Requires contextual operator review.',
      review_status: rawDet.review_status || rawDet.status || 'PENDING REVIEW',
      evidence_status: rawDet.evidence_status || 'AVAILABLE'
    },
    status: rawDet.review_status || rawDet.status || 'PENDING REVIEW',
    reviewStatus: rawDet.review_status || rawDet.status || 'PENDING REVIEW',
    box,
    bbox: rawDet.bbox || box,
    imagePosition: rawDet.imagePosition || {
      x: box.x,
      y: box.y,
      display: `X: ${Math.round(box.x)}%, Y: ${Math.round(box.y)}%`
    },
    survey_latitude: rawDet.survey_latitude ?? (hasGeo ? (rawDet.latitude ?? rawDet.geoLat) : null),
    survey_longitude: rawDet.survey_longitude ?? (hasGeo ? (rawDet.longitude ?? rawDet.geoLon) : null),
    has_target_geolocation: rawDet.has_target_geolocation || false,
    target_geolocation_note: rawDet.target_geolocation_note || (hasGeo ? 'Detection localized in sonar image-space with survey GPS anchor.' : 'Image-only sonar input.'),
    geoLat: rawDet.geoLat ?? rawDet.latitude ?? null,
    geoLon: rawDet.geoLon ?? rawDet.longitude ?? null,
    latitude: rawDet.latitude ?? rawDet.geoLat ?? null,
    longitude: rawDet.longitude ?? rawDet.geoLon ?? null,
    coordinateReference: rawDet.coordinateReference || (hasGeo ? 'WGS 84 (Geographic 2D - EPSG:4326)' : 'UNAVAILABLE'),
    metadataSource: rawDet.metadataSource || (hasGeo ? 'Survey Towfish GPS Anchor (Image-Space Detection)' : 'Image-only sonar input'),
    dimensions: `${((box.w || 10) * 0.3).toFixed(1)} m × ${((box.h || 10) * 0.2).toFixed(1)} m`,
    acousticShadow: `${((box.h || 10) * 0.4).toFixed(1)} m`,
    shadowLength: `${((box.h || 10) * 0.4).toFixed(1)} m`,
    acousticFeature: `Acoustic backscatter anomaly detected by ${rawDet.model || 'model'} (${displayClass})`,
    evidenceImage: evidenceUrl,
    model: rawDet.model,
    competing_hypotheses: rawDet.competing_hypotheses || []
  };
}

/**
 * POST /api/v1/analysis/analyze
 * Uploads an image for multi-model inference and persistence
 */
/**
 * Polls an asynchronous analysis job until completion or timeout
 */
export async function pollAnalysisJob(jobId, onProgress = null, maxTimeoutMs = 180000, signal = null) {
  const startTime = Date.now();
  const pollIntervalMs = 1500;

  while (Date.now() - startTime < maxTimeoutMs) {
    if (signal?.aborted) {
      throw new DOMException('Analysis polling was aborted', 'AbortError');
    }

    let response;
    try {
      response = await fetch(`${API_BASE_URL}/api/v1/analysis/jobs/${jobId}`, { signal });
    } catch (err) {
      if (signal?.aborted || err?.name === 'AbortError') {
        throw new DOMException('Analysis polling was aborted', 'AbortError');
      }
      await new Promise((r) => setTimeout(r, pollIntervalMs));
      continue;
    }

    if (response.status === 404) {
      throw new ApiError(`Job '${jobId}' was not found on server.`, 404);
    }

    if (!response.ok) {
      throw new ApiError(`Error polling job status (${response.status})`, response.status);
    }

    const jobData = await response.json();

    if (onProgress && typeof onProgress === 'function') {
      onProgress({
        progress: jobData.progress ?? 0,
        step: jobData.current_step || 'Processing...',
        status: jobData.status,
      });
    }

    if (jobData.status === 'completed') {
      return jobData.result;
    }

    if (jobData.status === 'failed') {
      throw new ApiError(
        jobData.error || 'Survey analysis job failed.',
        500,
        jobData,
        jobData.error || 'The analysis job encountered an error.'
      );
    }

    await new Promise((r) => setTimeout(r, pollIntervalMs));
  }

  throw new ApiError('Analysis job timed out on the server after 3 minutes.', 504);
}

/**
 * Safely downscales oversized sonar images in-browser to prevent backend Render OOM crashes.
 * Preserves full acoustic features while capping maximum dimension to 1280px.
 */
async function optimizeImageForUpload(file, maxDimension = 1280) {
  if (!file || typeof window === 'undefined' || !(file instanceof Blob) || !file.type.startsWith('image/')) {
    return file;
  }

  // If already reasonable size (under 600 KB and JPEG/WebP), don't touch
  if (file.size < 600 * 1024 && (file.type === 'image/jpeg' || file.type === 'image/webp')) {
    return file;
  }

  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;
      if (width <= maxDimension && height <= maxDimension && file.size < 900 * 1024) {
        resolve(file);
        return;
      }

      if (width > maxDimension || height > maxDimension) {
        if (width > height) {
          height = Math.round((height * maxDimension) / width);
          width = maxDimension;
        } else {
          width = Math.round((width * maxDimension) / height);
          height = maxDimension;
        }
      }

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(file);
            return;
          }
          const baseName = (file.name || 'sonar_swath').replace(/\.[^/.]+$/, '');
          const optimizedFile = new File([blob], `${baseName}.jpg`, {
            type: 'image/jpeg',
            lastModified: file.lastModified || Date.now(),
          });
          resolve(optimizedFile);
        },
        'image/jpeg',
        0.88
      );
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(file);
    };

    img.src = url;
  });
}

/**
 * Error response handler for sonar analysis API endpoints.
 */
async function handleResponseErrors(res) {
  const errorData = await res.json().catch(() => ({}));
  if (res.status === 422) throw new SonarValidationError(errorData);
  if (res.status === 415) {
    const msg = 'Unsupported image format. Please upload JPG, PNG, TIFF, BMP or WebP.';
    throw new ApiError(msg, 415, errorData, msg);
  }
  if (res.status === 400) {
    const msg = errorData.detail || 'Unable to process this request. Please check the image and metadata.';
    throw new ApiError(msg, 400, errorData, msg);
  }
}

/**
 * Executes multi-model side-scan sonar anomaly analysis on an image.
 */
export async function analyzeSonarImage(imageFile, options = {}) {
  if (!imageFile) {
    throw new ApiError('No file provided for analysis.', 400);
  }

  const signal = options?.signal;
  const uploadFile = await optimizeImageForUpload(imageFile);
  const formData = new FormData();
  formData.append('image', uploadFile, uploadFile.name || 'sonar_input.jpg');

  if (options.selected_models) {
    const modelsStr = Array.isArray(options.selected_models)
      ? options.selected_models.join(',')
      : options.selected_models;
    formData.append('selected_models', modelsStr);
  }

  if (options.confidence != null) formData.append('confidence', String(options.confidence));
  if (options.iou != null) formData.append('iou', String(options.iou));
  if (options.enable_seabed_gate != null) formData.append('enable_seabed_gate', String(options.enable_seabed_gate));
  if (options.seabed_clean_threshold != null) formData.append('seabed_clean_threshold', String(options.seabed_clean_threshold));
  if (options.latitude != null && options.latitude !== '') formData.append('latitude', String(options.latitude));
  if (options.longitude != null && options.longitude !== '') formData.append('longitude', String(options.longitude));
  if (options.depth != null && options.depth !== '') formData.append('depth', String(options.depth));
  if (options.heading != null && options.heading !== '') formData.append('heading', String(options.heading));
  if (options.timestamp != null && options.timestamp !== '') formData.append('timestamp', String(options.timestamp));

  // 1. Asynchronous Job Submission (Eliminates Render/Cloudflare 100s Timeouts)
  try {
    const jobSubmitResponse = await fetch(`${API_BASE_URL}/api/v1/analysis/jobs`, {
      method: 'POST',
      body: formData,
      signal,
    });

    if (jobSubmitResponse.status === 202) {
      const submission = await jobSubmitResponse.json();
      return await pollAnalysisJob(submission.job_id, options.onProgress, 180000, signal);
    }

    await handleResponseErrors(jobSubmitResponse);
  } catch (err) {
    if (signal?.aborted || err?.name === 'AbortError') {
      throw new DOMException('Analysis was aborted', 'AbortError');
    }
    if (err instanceof ApiError || err instanceof SonarValidationError) {
      throw err;
    }
    console.info('Async jobs endpoint unavailable, falling back to synchronous /analyze:', err.message);
  }

  // 2. Synchronous Fallback (/analyze)
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/analysis/analyze`, {
      method: 'POST',
      body: formData,
      signal,
    });
  } catch (err) {
    if (signal?.aborted || err?.name === 'AbortError') {
      throw new DOMException('Analysis was aborted', 'AbortError');
    }
    throw new ApiError(
      `Network connection failed: ${err.message}`,
      0,
      null,
      `Unable to reach the backend at ${API_BASE_URL}. If the service was sleeping on Render's free tier, it takes ~30-50s to spin up. Please wait a moment and try again.`
    );
  }

  if (response.status === 502 || response.status === 503 || response.status === 504) {
    const userMessage = 'The backend is currently waking up or temporarily unavailable on Render. Please wait ~30 seconds and retry.';
    throw new ApiError(userMessage, response.status, null, userMessage);
  }

  await handleResponseErrors(response);

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const userMessage = 'Something went wrong while processing the sonar image. Please try again.';
    throw new ApiError(userMessage, response.status, errorData, userMessage);
  }

  return await response.json();
}

/**
 * Analyzes multiple sonar images in sequence with live progress tracking,
 * filtering and categorizing images with abnormalities vs clean seabed.
 */
export async function analyzeBatchSonarImages(imageFiles = [], options = {}, onProgress = null) {
  if (!imageFiles || imageFiles.length === 0) {
    throw new ApiError('No files provided for batch analysis.', 400);
  }

  const signal = options?.signal;
  const total = imageFiles.length;
  const results = [];
  const flagged = [];
  const clean = [];
  const failed = [];

  for (let i = 0; i < total; i++) {
    if (signal?.aborted) {
      console.info('Batch analysis stopped early due to abort signal.');
      break;
    }

    const file = imageFiles[i];
    const previewUrl = URL.createObjectURL(file);

    if (onProgress && typeof onProgress === 'function') {
      onProgress({
        currentIndex: i + 1,
        total,
        currentFile: file,
        filename: file.name,
        progress: Math.round((i / total) * 100),
        phase: 'processing',
        flaggedCount: flagged.length,
        cleanCount: clean.length,
      });
    }

    // Apply user options, or let calibrated backend model-specific thresholds apply
    const batchOptions = { ...(options || {}) };

    try {
      const result = await analyzeSonarImage(file, { ...batchOptions, signal });
      if (signal?.aborted) break;

      const rawDetections = result?.detections || [];
      const detections = rawDetections.map((d, idx) =>
        mapBackendDetection(d, idx, result.analysis_id)
      );
      const detectionsCount = detections.length;

      const record = {
        id: result?.analysis_id || `ITEM-${i + 1}`,
        analysisId: result?.analysis_id,
        file,
        filename: file.name,
        size: file.size,
        previewUrl,
        detectionsCount,
        detections,
        rawResult: result,
        triage: result?.triage,
        hasAnomalies: detectionsCount > 0,
        isCleanTriage: result?.triage?.downstream_skipped === true,
        highestConfidence: result?.summary?.highest_confidence || (detectionsCount > 0 ? Math.max(...detections.map(d => d.confidence || 0)) : 0),
        categories: Array.from(new Set(detections.map(d => d.semantic_class_name || d.name || 'Anomaly'))),
        processedAt: new Date().toISOString(),
      };

      results.push(record);
      if (detectionsCount > 0) {
        flagged.push(record);
      } else {
        clean.push(record);
      }
    } catch (err) {
      if (signal?.aborted || err?.name === 'AbortError') {
        console.info(`Batch processing aborted on file ${file.name}`);
        break;
      }
      console.warn(`Batch item ${file.name} failed:`, err);
      const failedItem = {
        id: `ERR-${i + 1}`,
        file,
        filename: file.name,
        size: file.size,
        previewUrl,
        detectionsCount: 0,
        detections: [],
        hasAnomalies: false,
        isError: true,
        errorMessage: err.userFriendlyMessage || err.message || 'Failed validation/processing',
      };
      results.push(failedItem);
      failed.push(failedItem);
    }
  }

  const isCompleted = !signal?.aborted && (results.length + failed.length >= total);
  if (onProgress && typeof onProgress === 'function' && !signal?.aborted) {
    onProgress({
      currentIndex: total,
      total,
      progress: 100,
      phase: 'completed',
      flaggedCount: flagged.length,
      cleanCount: clean.length,
    });
  }

  return {
    totalScanned: results.length + failed.length,
    totalPlanned: total,
    isAborted: Boolean(signal?.aborted),
    isCompleted,
    flaggedCount: flagged.length,
    cleanCount: clean.length,
    failedCount: failed.length,
    flagged,
    clean,
    failed,
    all: results,
  };
}

/**
 * GET /api/v1/analysis
 * Returns paginated list of previous survey analyses
 */
export async function getAnalyses(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', String(params.page));
  if (params.page_size) query.append('page_size', String(params.page_size));
  if (params.status) query.append('status', params.status);
  if (params.detection_type) query.append('detection_type', params.detection_type);

  const qs = query.toString();
  const url = `${API_BASE_URL}/api/v1/analysis${qs ? `?${qs}` : ''}`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new ApiError(`Failed to fetch analyses (${response.status})`, response.status);
    }
    return await response.json();
  } catch (err) {
    console.warn('Failed to fetch analyses from backend:', err.message);
    return { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
  }
}

/**
 * GET /api/v1/analysis/{analysis_id}
 * Retrieves full details for a single analysis record
 */
export async function getAnalysisById(analysisId) {
  if (!analysisId) return null;
  const url = `${API_BASE_URL}/api/v1/analysis/${analysisId}`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new ApiError(`Analysis with ID '${analysisId}' not found`, response.status);
  }
  return await response.json();
}

/**
 * Build URL to access stored evidence image
 */
export function getEvidenceUrl(analysisId) {
  if (!analysisId) return null;
  return `${API_BASE_URL}/api/v1/analysis/${analysisId}/evidence`;
}

/**
 * Health check endpoint
 */
export async function checkBackendHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/health`);
    if (!response.ok) return { status: 'unhealthy', code: response.status };
    return await response.json();
  } catch (err) {
    return { status: 'offline', error: err.message };
  }
}

/**
 * GET /api/v1/models
 * Returns available models and registered metadata
 */
export async function getModels() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/models`);
    if (!response.ok) throw new ApiError(`Failed to fetch models (${response.status})`, response.status);
    return await response.json();
  } catch (err) {
    console.warn('Failed to fetch models from backend:', err.message);
    return {
      models: [
        { id: 'cylinder', name: 'Cylinder', status: 'available' },
        { id: 'ghostvision', name: 'GhostVision', status: 'available' },
        { id: 'mines', name: 'Mines', status: 'available' },
        { id: 'shipwreck', name: 'Shipwreck', status: 'available' },
        { id: 'subpipes', name: 'SubPipes', status: 'available' }
      ],
      unavailable_models: ['natural_seabed'],
      total: 5
    };
  }
}
