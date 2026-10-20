import { beforeEach, describe, expect, it, vi } from 'vitest';

// The handlers thin-wrap the API client; mock it to test validation and
// error mapping without network.
vi.mock('$lib/api', () => {
	return {
		ApiError: class extends Error {
			status: number;
			constructor(status: number, message: string) {
				super(message);
				this.status = status;
			}
		},
		createKeyword: vi.fn(),
		updateKeyword: vi.fn(),
		deleteKeyword: vi.fn()
	};
});

import { ApiError, createKeyword, deleteKeyword, updateKeyword } from '$lib/api';
import { handleKeywordCreate, handleKeywordDelete, handleKeywordToggle } from './keyword-actions';

function formWith(entries: Record<string, string>): Request {
	const params = new URLSearchParams(entries);
	return new Request('http://localhost/test', { method: 'POST', body: params });
}

const mockedCreate = vi.mocked(createKeyword);
const mockedToggle = vi.mocked(updateKeyword);
const mockedDelete = vi.mocked(deleteKeyword);

beforeEach(() => {
	vi.clearAllMocks();
});


/** ActionFailure hides payload behind `.data`; successes carry it directly. */
function view(result: unknown): { ok?: boolean; action?: string; status?: number } {
	const r = result as {
		status?: number;
		ok?: boolean;
		action?: string;
		data?: { ok: boolean; action: string };
	};
	if (r && typeof r === 'object' && 'data' in r && r.data) {
		return { ok: r.data.ok, action: r.data.action, status: r.status };
	}
	return { ok: r.ok, action: r.action };
}

describe('handleKeywordCreate', () => {
	it('rejects empty text', async () => {
		const result = await handleKeywordCreate(formWith({ text: '  ' }));
		expect(view(result)).toMatchObject({ ok: false, status: 400 });
	});

	it('rejects text over 500 chars', async () => {
		const result = await handleKeywordCreate(formWith({ text: 'x'.repeat(501) }));
		expect(view(result)).toMatchObject({ ok: false, status: 400 });
	});

	it('normalizes the language and echoes the created row', async () => {
		mockedCreate.mockResolvedValueOnce({
			id: 1,
			text: 'BUAP',
			language: 'es',
			is_active: true,
			created_at: '2026-10-19T00:00:00Z'
		});
		const result = await handleKeywordCreate(formWith({ text: ' BUAP ', language: 'zz' }));
		expect(mockedCreate).toHaveBeenCalledWith({ text: 'BUAP', language: 'es' });
		expect(view(result)).toMatchObject({ ok: true, action: 'create' });
	});

	it('maps ApiError status into the failure', async () => {
		mockedCreate.mockRejectedValueOnce(new ApiError(409, 'dup'));
		const result = await handleKeywordCreate(formWith({ text: 'BUAP' }));
		expect(view(result)).toMatchObject({ ok: false, status: 409 });
	});
});

describe('handleKeywordToggle', () => {
	it('rejects invalid ids', async () => {
		const result = await handleKeywordToggle(formWith({ id: 'x', is_active: '1' }));
		expect(view(result)).toMatchObject({ ok: false, status: 400 });
	});

	it('passes the boolean through', async () => {
		mockedToggle.mockResolvedValueOnce({
			id: 7,
			text: 'a',
			language: 'es',
			is_active: false,
			created_at: 'x'
		});
		const result = await handleKeywordToggle(formWith({ id: '7', is_active: '0' }));
		expect(mockedToggle).toHaveBeenCalledWith(7, { is_active: false });
		expect(view(result)).toMatchObject({ ok: true, action: 'toggle' });
	});
});

describe('handleKeywordDelete', () => {
	it('rejects invalid ids and maps errors', async () => {
		expect(view(await handleKeywordDelete(formWith({ id: '0' })))).toMatchObject({ ok: false });
		mockedDelete.mockRejectedValueOnce(new ApiError(409, 'referenced'));
		const result = await handleKeywordDelete(formWith({ id: '3' }));
		expect(view(result)).toMatchObject({ ok: false, status: 409 });
	});
});
