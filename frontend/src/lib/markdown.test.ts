import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
	it('renders GFM tables', () => {
		const html = renderMarkdown('| Hop | g |\n|---|---|\n| Amarillo | 20 |');
		expect(html).toContain('<table>');
		expect(html).toContain('<td>Amarillo</td>');
	});

	it('shows raw HTML as text', () => {
		const html = renderMarkdown('hi <img src=x onerror=alert(1)>');
		expect(html).not.toContain('<img');
		expect(html).toContain('&lt;img');
	});

	it('drops non-http links but keeps safe ones', () => {
		expect(renderMarkdown('[x](javascript:alert(1))')).not.toContain('<a');
		expect(renderMarkdown('[BJCP](https://bjcp.org)')).toContain('href="https://bjcp.org"');
	});

	it('keeps bold, lists and empty input', () => {
		expect(renderMarkdown('**IBU**')).toContain('<strong>IBU</strong>');
		expect(renderMarkdown('- a\n- b')).toContain('<li>a</li>');
		expect(renderMarkdown('')).toBe('');
	});
});
