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

  // Normalized percentage box coordinates for CSS overlays
  const box = {
    x: rawDet.bbox?.x ?? 0,
    y: rawDet.bbox?.y ?? 0,
    w: rawDet.bbox?.w ?? 0,
    h: rawDet.bbox?.h ?? 0
  };

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
    model: rawDet.model
  };
}

/**
 * POST /api/v1/analysis/analyze
 * Uploads an image for multi-model inference and persistence
 */
/**
 * Polls an asynchronous analysis job until completion or timeout
 */
export async function pollAnalysisJob(jobId, onProgress = null, maxTimeoutMs = 180000) {
  const startTime = Date.now();
  const pollIntervalMs = 1500;

  while (Date.now() - startTime < maxTimeoutMs) {
    let response;
    try {
      response = await fetch(`${API_BASE_URL}/api/v1/analysis/jobs/${jobId}`);
    } catch (err) {
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
 * POST /api/v1/analysis/jobs (with fallback to /api/v1/analysis/analyze)
 * Uploads an image for multi-model inference and persistence without gateway timeouts
 */
export async function analyzeSonarImage(imageFile, options = {}) {
  if (!imageFile) {
    throw new ApiError('No file provided for analysis.', 400);
  }

  const formData = new FormData();
  formData.append('image', imageFile, imageFile.name || 'sonar_input.png');

  if (options.selected_models) {
    const modelsStr = Array.isArray(options.selected_models)
      ? options.selected_models.join(',')
      : options.selected_models;
    formData.append('selected_models', modelsStr);
  }

  if (options.confidence != null) formData.append('confidence', String(options.confidence));
  if (options.iou != null) formData.append('iou', String(options.iou));
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
    });

    if (jobSubmitResponse.status === 202) {
      const submission = await jobSubmitResponse.json();
      return await pollAnalysisJob(submission.job_id, options.onProgress);
    }

    // Pass-through validation errors from immediate pre-check
    if (jobSubmitResponse.status === 422) {
      const errorData = await jobSubmitResponse.json().catch(() => ({}));
      throw new SonarValidationError(errorData);
    }
    if (jobSubmitResponse.status === 415) {
      const errorData = await jobSubmitResponse.json().catch(() => ({}));
      const userMessage = 'Unsupported image format. Please upload JPG, PNG, TIFF, BMP or WebP.';
      throw new ApiError(userMessage, 415, errorData, userMessage);
    }
    if (jobSubmitResponse.status === 400) {
      const errorData = await jobSubmitResponse.json().catch(() => ({}));
      const userMessage = errorData.detail || 'Unable to process this request. Please check the image and metadata.';
      throw new ApiError(userMessage, 400, errorData, userMessage);
    }
  } catch (err) {
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
    });
  } catch (err) {
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

  if (response.status === 422) {
    const errorData = await response.json().catch(() => ({}));
    throw new SonarValidationError(errorData);
  }

  if (response.status === 415) {
    const errorData = await response.json().catch(() => ({}));
    const userMessage = 'Unsupported image format. Please upload JPG, PNG, TIFF, BMP or WebP.';
    throw new ApiError(userMessage, 415, errorData, userMessage);
  }

  if (response.status === 400) {
    const errorData = await response.json().catch(() => ({}));
    const userMessage = errorData.detail || 'Unable to process this request. Please check the image, metadata and selected models.';
    throw new ApiError(userMessage, 400, errorData, userMessage);
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const userMessage = 'Something went wrong while processing the sonar image. Please try again.';
    throw new ApiError(userMessage, response.status, errorData, userMessage);
  }

  return await response.json();
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
