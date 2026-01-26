/**
 * BrewSignal Frontend Configuration
 *
 * Supports two deployment modes:
 * - local: Single-user RPi deployment (no auth required)
 * - cloud: Multi-tenant SaaS (Supabase Auth)
 */

// Deployment mode from environment
export const DEPLOYMENT_MODE = import.meta.env.VITE_DEPLOYMENT_MODE || 'local';

// Convenience checks
export const isCloudMode = DEPLOYMENT_MODE === 'cloud';
export const isLocalMode = DEPLOYMENT_MODE === 'local';

// API URL - defaults to same origin for local, explicit URL for cloud
export const API_URL = import.meta.env.VITE_API_URL || '';

// Supabase configuration (cloud mode only)
export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

// Feature flags based on deployment mode
export const config = {
  // Auth is only enabled in cloud mode
  authEnabled: isCloudMode,

  // Multi-tenancy is only available in cloud mode
  multiTenant: isCloudMode,

  // Local mode shows device setup, cloud mode shows account linking
  showDeviceSetup: isLocalMode,

  // Local mode can use direct BLE scanning
  directBLEEnabled: isLocalMode,

  // Cloud mode uses gateways for device communication
  gatewayMode: isCloudMode,
} as const;
