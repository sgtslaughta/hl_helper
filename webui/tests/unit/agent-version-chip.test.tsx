import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AgentVersionChip } from '@/components/hosts/agent-version-chip';

describe('AgentVersionChip', () => {
  it('renders unknown when current is missing', () => {
    render(<AgentVersionChip />);
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });

  it('renders current version when provided', () => {
    render(<AgentVersionChip current="1.2.3" />);
    expect(screen.getByText('1.2.3')).toBeInTheDocument();
  });

  it('shows up arrow when drift exists and not updating', () => {
    render(<AgentVersionChip current="1.2.3" latest="1.2.4" status="idle" />);
    expect(screen.getByText(/1\.2\.3 ↑/)).toBeInTheDocument();
  });

  it('shows ellipsis when updating', () => {
    render(<AgentVersionChip current="1.2.3" latest="1.2.4" status="updating" />);
    expect(screen.getByText(/1\.2\.3 …/)).toBeInTheDocument();
  });

  it('shows ellipsis over up arrow when updating even with drift', () => {
    render(<AgentVersionChip current="1.2.3" latest="1.2.5" status="in_progress" />);
    expect(screen.getByText(/1\.2\.3 …/)).toBeInTheDocument();
  });

  it('renders outline variant by default', () => {
    const { container } = render(<AgentVersionChip current="1.2.3" />);
    const badge = container.querySelector('[class*="badge"]');
    expect(badge?.className).toMatch(/outline/);
  });

  it('renders default variant when updating', () => {
    const { container } = render(<AgentVersionChip current="1.2.3" status="rolling_out" />);
    const badge = container.querySelector('[class*="badge"]');
    expect(badge?.className).toMatch(/default/);
  });

  it('renders secondary variant when drift and not updating', () => {
    const { container } = render(<AgentVersionChip current="1.2.3" latest="1.2.4" status="idle" />);
    const badge = container.querySelector('[class*="badge"]');
    expect(badge?.className).toMatch(/secondary/);
  });

  it('displays status in title attribute', () => {
    const { container } = render(<AgentVersionChip current="1.2.3" status="idle" />);
    const badge = container.querySelector('span[title]');
    expect(badge).toHaveAttribute('title', 'status: idle');
  });

  it('no title when status is missing', () => {
    const { container } = render(<AgentVersionChip current="1.2.3" />);
    const badge = container.querySelector('span[title]');
    expect(badge).not.toHaveAttribute('title');
  });

  it('no up arrow when no latest version', () => {
    render(<AgentVersionChip current="1.2.3" status="idle" />);
    expect(screen.getByText(/^1\.2\.3$/)).toBeInTheDocument();
  });
});
