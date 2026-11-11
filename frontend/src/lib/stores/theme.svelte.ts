// Theme store. Dark is the default (no data-theme attribute); light sets data-theme="light".
export const STORAGE_KEY = 'brewsignal-theme';

// Light theme stays hidden until every screen is migrated to the new tokens.
// Tracked in bead tilt_ui-nv1r. Flip to true to expose the toggle in the shell.
export const SHOW_THEME_TOGGLE = true;

export type Theme = 'dark' | 'light';

function readStored(): Theme {
	try {
		return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
	} catch {
		return 'dark';
	}
}

export const themeState = $state<{ theme: Theme }>({ theme: 'dark' });

export function setTheme(theme: Theme) {
	themeState.theme = theme;
	if (typeof document !== 'undefined') {
		if (theme === 'light') document.documentElement.dataset.theme = 'light';
		else delete document.documentElement.dataset.theme;
	}
	try {
		localStorage.setItem(STORAGE_KEY, theme);
	} catch {
		/* storage unavailable: theme still applies for this session */
	}
}

/** Call once on mount to apply the persisted theme. */
export function initTheme() {
	setTheme(readStored());
}
