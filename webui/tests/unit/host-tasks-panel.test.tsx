import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HostTasksPanel } from '@/components/hosts/host-tasks-panel';

vi.mock('@/lib/rbac', () => ({
  useCanPerform: () => ({ allowed: true, reason: '', principal: 'u' }),
}));

vi.mock('@/lib/auth', () => ({
  useAuth: () => ({ user: null }),
}));

vi.mock('@/components/tasks/task-result-preview', () => ({
  TaskResultPreview: ({ taskId, hostId }: { taskId: string; hostId: string }) => (
    <div data-testid="preview" data-task={taskId} data-host={hostId}>
      preview
    </div>
  ),
}));

const tasks = [
  { id: 't1', kind: 'shell_exec', status: 'completed', risk: 'low', created_at: '2026-05-06T18:00Z', summary: 'uname -a' },
  { id: 't2', kind: 'shell_exec', status: 'running', risk: 'low', created_at: '2026-05-06T18:01Z', summary: 'apt upgrade' },
  { id: 't3', kind: 'agent_update', status: 'pending', risk: 'medium', created_at: '2026-05-06T18:02Z', summary: undefined, payload: { release_id: 'abc123def456', force: false, reason: 'Security update' }, host_update_status: 'queued' },
];

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes('/v1/tasks?host_id=')) {
      return new Response(JSON.stringify({ items: tasks, next_cursor: null }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }
    return new Response(JSON.stringify({}), { status: 200 });
  });
});

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('HostTasksPanel inline expansion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it('clicking a row inserts a preview row', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const row = await screen.findByText('uname -a');
    fireEvent.click(row.closest('tr') as HTMLElement);
    const preview = await screen.findByTestId('preview');
    expect(preview).toHaveAttribute('data-task', 't1');
    expect(preview).toHaveAttribute('data-host', 'h1');
  });

  it('clicking the same row again collapses the preview', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const row = (await screen.findByText('uname -a')).closest('tr') as HTMLElement;
    fireEvent.click(row);
    expect(await screen.findByTestId('preview')).toBeInTheDocument();
    fireEvent.click(row);
    expect(screen.queryByTestId('preview')).not.toBeInTheDocument();
  });

  it('clicking another row collapses the prior preview and opens the new one', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const row1 = (await screen.findByText('uname -a')).closest('tr') as HTMLElement;
    const row2 = (await screen.findByText('apt upgrade')).closest('tr') as HTMLElement;
    fireEvent.click(row1);
    fireEvent.click(row2);
    const previews = screen.getAllByTestId('preview');
    expect(previews).toHaveLength(1);
    expect(previews[0]).toHaveAttribute('data-task', 't2');
  });

  it('clicking the open-detail link does NOT toggle expansion', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const row = (await screen.findByText('uname -a')).closest('tr') as HTMLElement;
    fireEvent.click(row);
    expect(await screen.findByTestId('preview')).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: /open task detail/i });
    fireEvent.click(links[0]);
    expect(screen.queryByTestId('preview')).toBeInTheDocument();
  });

  it('Enter key on focused row toggles expansion', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const row = (await screen.findByText('uname -a')).closest('tr') as HTMLElement;
    row.focus();
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(await screen.findByTestId('preview')).toBeInTheDocument();
  });

  it('renders agent_update task with release ID, status, and reason', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const detail = await screen.findByText(/Update to release/);
    expect(detail).toBeInTheDocument();
    expect(screen.getByText(/abc123de/)).toBeInTheDocument();
    expect(screen.getByText('Security update')).toBeInTheDocument();
  });
});

describe('HostTasksPanel — elevated execution', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reason field is hidden by default', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const newTaskBtn = await screen.findByRole('button', { name: /new task/i });
    fireEvent.click(newTaskBtn);
    expect(screen.queryByPlaceholderText(/Why does this need root/)).not.toBeInTheDocument();
  });

  it('shows reason field + warn banner when "Run elevated" is checked', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const newTaskBtn = await screen.findByRole('button', { name: /new task/i });
    fireEvent.click(newTaskBtn);
    const elevatedCheckbox = await screen.findByRole('checkbox', { name: /run elevated/i });
    fireEvent.click(elevatedCheckbox);
    expect(await screen.findByPlaceholderText(/Why does this need root/)).toBeInTheDocument();
    expect(screen.getByText(/ELEVATED EXECUTION/)).toBeInTheDocument();
  });

  it('Confirm button is disabled when reason is too short', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const newTaskBtn = await screen.findByRole('button', { name: /new task/i });
    fireEvent.click(newTaskBtn);
    const elevatedCheckbox = await screen.findByRole('checkbox', { name: /run elevated/i });
    fireEvent.click(elevatedCheckbox);
    const reasonInput = await screen.findByPlaceholderText(/Why does this need root/);
    fireEvent.change(reasonInput, { target: { value: 'short' } });
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    expect(confirmBtn).toBeDisabled();
  });

  it('Confirm button is enabled when reason is valid (8+ chars)', async () => {
    render(wrap(<HostTasksPanel hostId="h1" />));
    const newTaskBtn = await screen.findByRole('button', { name: /new task/i });
    fireEvent.click(newTaskBtn);
    const elevatedCheckbox = await screen.findByRole('checkbox', { name: /run elevated/i });
    fireEvent.click(elevatedCheckbox);
    const reasonInput = await screen.findByPlaceholderText(/Why does this need root/);
    fireEvent.change(reasonInput, { target: { value: 'longEnough' } });
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    expect(confirmBtn).not.toBeDisabled();
  });
});
