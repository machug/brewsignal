import { Marked } from 'marked';

const escapeHtml = (s: string) =>
	s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// Chat markdown (GFM: tables, lists, code). Output goes into {@html}, and the
// text comes from an LLM that has seen tool results, so raw HTML is shown as
// text and only http(s)/relative links become anchors.
const md = new Marked({
	gfm: true,
	breaks: true,
	renderer: {
		html({ text }) {
			return escapeHtml(text);
		},
		link({ href, tokens }) {
			const label = this.parser.parseInline(tokens);
			if (!/^(https?:\/\/|\/)/i.test(href)) return label;
			return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
		}
	}
});

export function renderMarkdown(text: string): string {
	return text ? (md.parse(text, { async: false }) as string) : '';
}
