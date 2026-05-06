import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TaskResultPreview } from '@/components/tasks/task-result-preview';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const baseDetail = {
  host_id: 'h1',
  command_id: 'c1',
  status: 'completed',
  exit_code: 0,
  received_at: '2026-05-06T18:00:00Z',
  stdout: 'hello world',
  stdout_truncated: false,
  stderr: '',
  stderr_truncated: false,
  rejection_reason: null,
};

describe('TaskResultPreview', () => {
  it('shows stdout and exit code from query data', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(baseDetail), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    render(wrap(<TaskResultPreview taskId="t1" hostId="h1" />));
    expect(await screen.findByText('hello world')).toBeInTheDocument();
    expect(screen.getByText(/exit/i)).toBeInTheDocument();
  });

  it('shows truncation badge when stdout_truncated', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...baseDetail, stdout: 'x'.repeat(80), stdout_truncated: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    render(wrap(<TaskResultPreview taskId="t1" hostId="h1" />));
    expect(await screen.findByText(/truncated/i)).toBeInTheDocument();
  });

  it('shows error pill on failed query', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('boom', { status: 500 }));
    render(wrap(<TaskResultPreview taskId="t1" hostId="h1" />));
    expect(await screen.findByText(/failed to load/i)).toBeInTheDocument();
  });

  it('renders link to full detail at /tasks/<id>', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(baseDetail), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    render(wrap(<TaskResultPreview taskId="t1" hostId="h1" />));
    const link = await screen.findByRole('link', { name: /open full detail/i });
    expect(link).toHaveAttribute('href', '/tasks/t1');
  });
});
