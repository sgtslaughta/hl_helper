import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PaneChrome, type PaneTab } from '@/components/hosts/mission-control/pane-chrome';

const tabs: PaneTab[] = [
  { key: 'a', label: 'Alpha', hotkey: '1' },
  { key: 'b', label: 'Beta', hotkey: '2', pill: { text: '3', tone: 'info' } },
  { key: 'c', label: 'Gamma', hotkey: '3' },
  { key: 'd', label: 'Delta', hotkey: '4' },
  { key: 'e', label: 'Epsilon', hotkey: '5', overflow: true },
];

describe('PaneChrome', () => {
  it('renders primary tabs and groups overflow into More menu', () => {
    render(<PaneChrome label="Focus" tabs={tabs} value="a" onChange={() => {}} actions={[]}>body</PaneChrome>);
    expect(screen.getByRole('tab', { name: /Alpha/ })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Epsilon/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /More/ })).toBeInTheDocument();
  });

  it('marks active tab with aria-selected', () => {
    render(<PaneChrome label="Focus" tabs={tabs} value="b" onChange={() => {}} actions={[]}>x</PaneChrome>);
    expect(screen.getByRole('tab', { name: /Beta/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('fires onChange when tab clicked', () => {
    const onChange = vi.fn();
    render(<PaneChrome label="Focus" tabs={tabs} value="a" onChange={onChange} actions={[]}>x</PaneChrome>);
    fireEvent.click(screen.getByRole('tab', { name: /Beta/ }));
    expect(onChange).toHaveBeenCalledWith('b');
  });

  it('renders pill on tab with tone class', () => {
    render(<PaneChrome label="Focus" tabs={tabs} value="a" onChange={() => {}} actions={[]}>x</PaneChrome>);
    const pills = screen.getAllByText('3');
    const pill = pills.find(el => el.hasAttribute('data-tone'));
    expect(pill).toHaveAttribute('data-tone', 'info');
  });

  it('renders right-side action buttons with aria-label', () => {
    const onRefresh = vi.fn();
    render(
      <PaneChrome
        label="Focus"
        tabs={tabs}
        value="a"
        onChange={() => {}}
        actions={[{ icon: '↻', label: 'Refresh', onClick: onRefresh }]}
      >
        x
      </PaneChrome>,
    );
    const btn = screen.getByRole('button', { name: 'Refresh' });
    fireEvent.click(btn);
    expect(onRefresh).toHaveBeenCalled();
  });

  it('renders body content', () => {
    render(<PaneChrome label="Focus" tabs={tabs} value="a" onChange={() => {}} actions={[]}>HELLO</PaneChrome>);
    expect(screen.getByText('HELLO')).toBeInTheDocument();
  });

  it('shows active overflow tab label in More trigger', () => {
    render(<PaneChrome label="Focus" tabs={tabs} value="e" onChange={() => {}} actions={[]}>x</PaneChrome>);
    expect(screen.getByRole('button', { name: /Epsilon/ })).toBeInTheDocument();
  });
});
