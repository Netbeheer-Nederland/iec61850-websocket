/**
 * API Service for BFF Backend
 * This service provides a standardized way to execute API calls through the BFF's /api/execute endpoint
 */

// API Definitions - all available endpoints that can be called through execute
const API_DEFINITIONS = [
  // Connection management
  { id: 'connect', label: 'POST /api/connect', method: 'POST', path: '/api/connect' },
  { id: 'disconnect', label: 'POST /api/disconnect', method: 'POST', path: '/api/disconnect' },
  
  // Model operations
  { id: 'model-tree', label: 'POST /api/model/tree', method: 'POST', path: '/api/model/tree' },
  { id: 'data-definition', label: 'POST /api/getDataDefinition', method: 'POST', path: '/api/getDataDefinition' },
  
  // Data operations
  { id: 'read', label: 'POST /api/readvalue', method: 'POST', path: '/api/readvalue' },
  { id: 'write', label: 'POST /api/writevalue', method: 'POST', path: '/api/writevalue' },
  
  // Dataset operations
  { id: 'dataset-directory', label: 'POST /api/getDataSetDirectory', method: 'POST', path: '/api/getDataSetDirectory' },
  
  // Logs and actions
  { id: 'actions-logs', label: 'GET /api/actions-logs', method: 'GET', path: '/api/actions-logs' },
  { id: 'clear-logs', label: 'POST /api/clear-logs', method: 'POST', path: '/api/clear-logs' },
  
  // Status
  { id: 'status', label: 'GET /api/status', method: 'GET', path: '/api/status' },
  
  // Control operations
  { id: 'operate', label: 'POST /api/operate', method: 'POST', path: '/api/operate' },
  
  // Report Control Blocks (RCB)
  { id: 'urcb-read', label: 'POST /api/urcb-read', method: 'POST', path: '/api/urcb-read' },
  { id: 'brcb-read', label: 'POST /api/brcb-read', method: 'POST', path: '/api/brcb-read' },
  { id: 'brcb-write', label: 'POST /api/brcb-write', method: 'POST', path: '/api/brcb-write' },
  { id: 'urcb-write', label: 'POST /api/urcb-write', method: 'POST', path: '/api/urcb-write' },
  
  // Health check
  { id: 'health', label: 'GET /api/health', method: 'GET', path: '/api/health' },
  
  // ACSI Server operations
  { id: 'start', label: 'POST /api/start', method: 'POST', path: '/api/start' },
  { id: 'stop', label: 'POST /api/stop', method: 'POST', path: '/api/stop' },
  { id: 'model', label: 'GET /api/model', method: 'GET', path: '/api/model' },
  { id: 'update-iedmodel', label: 'POST /api/update-iedmodel', method: 'POST', path: '/api/update-iedmodel' },
  
  // OAuth configuration
  { id: 'reconfig-oauth', label: 'POST /api/reconfig-oauth', method: 'POST', path: '/api/reconfig-oauth' },
  { id: 'reconfig-connection', label: 'POST /api/reconfig-connection', method: 'POST', path: '/api/reconfig-connection' },
  { id: 'oauth-status', label: 'GET /api/oauth-status', method: 'GET', path: '/api/oauth-status' },
  
  // Messages operations
  { id: 'messages', label: 'GET /api/messages', method: 'GET', path: '/api/messages' },
  { id: 'clear-messages', label: 'POST /api/clear-messages', method: 'POST', path: '/api/clear-messages' },

  // Properties 
  { id: 'properties', label: 'GET /api/properties', method: 'GET', path: '/api/properties' },
];

/**
 * Get API definition by ID
 * @param {string} id - The API ID
 * @returns {object|null} The API definition object or null if not found
 */
export const getApiById = (id) => API_DEFINITIONS.find(api => api.id === id);

/**
 * Get BFF base URL from localStorage or use defaults
 * @returns {string} The BFF base URL
 */
export const getBffBaseUrl = () => {
  let savedSettings = {};
  try {
    savedSettings = JSON.parse(localStorage.getItem('rti-hmi-settings') || '{}') || {};
  } catch (e) {
    console.warn(`Failed to parse rti-hmi-settings: ${e.message}`);
  }
  const host = localStorage.getItem('bffHost') || savedSettings.bffHost || 'localhost';
  const port = localStorage.getItem('bffPort') || savedSettings.bffPort || '5000';
  return `http://${host}:${port}`;
};

/**
 * Build BFF API URL
 * @param {string} path - The API path
 * @param {string|null} targetValue - Optional target value (host:port)
 * @returns {string} The full API URL
 */
export const buildBffApiUrl = (path, targetValue = null) => {
  const baseUrl = getBffBaseUrl();
  if (!String(path || '').startsWith('/api/')) {
    throw new Error(`Blocked non-BFF API path: ${path}`);
  }
  const url = new URL(`${baseUrl}${path}`);
  if (targetValue) {
    url.searchParams.set('target', targetValue);
  }
  return url.toString();
};

/**
 * Execute an API call through the BFF's /api/execute endpoint
 * This is the main function that all API calls should use
 * 
 * @param {string} apiId - The API ID from API_DEFINITIONS
 * @param {string} targetValue - The target endpoint (host:port)
 * @param {object|null} bodyOverride - Optional request body
 * @param {object} options - Additional options
 * @param {boolean} options.useDirect - If true, call the endpoint directly instead of through /api/execute
 * @returns {Promise<object|null>} The API response object with ok, status, payload, rawText
 */
export const executeApiCall = async (apiId, targetValue = null, bodyOverride = null, options = {}) => {
  const { useDirect = false } = options;
  const api = getApiById(apiId);
  
  if (!api) {
    console.error(`API ${apiId} not found`);
    return null;
  }
  
  try {
    let url;
    if (useDirect) {
      // Direct endpoint call (for cases where /api/execute is not available)
      url = buildBffApiUrl(api.path, targetValue);
    } else {
      // Use /api/execute endpoint
      url = buildBffApiUrl('/api/execute');
    }
    
    const requestOptions = {
      method: useDirect ? api.method : 'POST',
      headers: { 'Content-Type': 'application/json' },
    };
    
    if (useDirect) {
      // For direct calls, send body directly
      if (api.method !== 'GET' && bodyOverride) {
        requestOptions.body = JSON.stringify(bodyOverride);
      }
    } else {
      // For /api/execute, send the execution request
      const payload = {
        target: targetValue,
        method: api.method,
        path: api.path,
      };
      if (bodyOverride) {
        payload.body = bodyOverride;
      }
      requestOptions.body = JSON.stringify(payload);
    }
    
    const response = await fetch(url, requestOptions);
    const rawText = await response.text();
    let parsedPayload = null;
    
    try {
      parsedPayload = JSON.parse(rawText);
    } catch (e) {
      // Keep raw text for non-JSON responses
      console.warn(`Failed to parse response as JSON: ${e.message}`);
    }
    
    return {
      ok: response.ok,
      status: response.status,
      payload: parsedPayload,
      rawText,
    };
  } catch (error) {
    console.error(`Request failed for ${api.label}:`, error.message || error);
    return null;
  }
};

/**
 * Check if BFF is healthy
 * @returns {Promise<boolean>} True if BFF is healthy
 */
export const ensureBffHealthy = async () => {
  try {
    const healthUrl = buildBffApiUrl('/api/health');
    const response = await fetch(healthUrl, { method: 'GET' });
    
    if (!response.ok) {
      throw new Error(`BFF health check failed with HTTP ${response.status}`);
    }
    
    const payload = await response.json();
    const bffStatus = payload?.bff?.status;
    
    if (String(bffStatus || '').toLowerCase() !== 'ok') {
      throw new Error('BFF health check returned non-ok status');
    }
    
    return true;
  } catch (error) {
    console.error('BFF health check failed:', error.message);
    throw error;
  }
};

/**
 * Build target value string from host and port
 * @param {string} host - The host
 * @param {number} port - The port
 * @returns {string} The target value (host:port)
 */
export const buildTargetValue = (host, port) => {
  if (!host || port === undefined || port === null) {
    return '';
  }
  return `${host}:${port}`;
};

/**
 * Get default target from endpoint object
 * @param {object} endpoint - The endpoint object with host and port properties
 * @returns {string} The target value (host:port)
 */
export const getDefaultTargetFromEndpoint = (endpoint) => {
  if (!endpoint) {
    return '';
  }
  return buildTargetValue(endpoint.host, endpoint.port);
};

export default {
  getApiById,
  getBffBaseUrl,
  buildBffApiUrl,
  executeApiCall,
  ensureBffHealthy,
  buildTargetValue,
  getDefaultTargetFromEndpoint,
  API_DEFINITIONS,
};
