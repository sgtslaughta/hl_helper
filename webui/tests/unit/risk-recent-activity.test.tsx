import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RiskRecentActivity } from '@/components/hosts/risk/recent-activity';
import type { AuditEntry } from '@/hooks/use-host-audit-by-action';

describe('RiskRecentActivity', () => {
	it('renders empty state when no entries', () => {
		render(<RiskRecentActivity entries={[]} />);
		expect(screen.getByText('No risk recomputes recorded yet.')).toBeInTheDocument();
	});

	it('renders entry with level transition', () => {
		const entries: AuditEntry[] = [
			{
				sequence: 1,
				timestamp: '2026-05-09T10:00:00Z',
				actor: 'system',
				action: 'risk.recomputed',
				subject: 'host1',
				payload: {
					score: 45,
					level: 'moderate',
					score_prev: 35,
					level_prev: 'stable',
					trigger_reason: 'CVE exposure',
				},
			},
		];
		render(<RiskRecentActivity entries={entries} />);
		expect(screen.getByText(/stable → moderate/)).toBeInTheDocument();
		expect(screen.getByText(/CVE exposure/)).toBeInTheDocument();
		expect(screen.getByText(/\+10/)).toBeInTheDocument();
	});

	it('renders entry without level transition', () => {
		const entries: AuditEntry[] = [
			{
				sequence: 2,
				timestamp: '2026-05-09T10:00:00Z',
				actor: 'system',
				action: 'risk.recomputed',
				subject: 'host1',
				payload: {
					score: 50,
					level: 'moderate',
					score_prev: 52,
					level_prev: 'moderate',
					trigger_reason: 'Score adjustment',
				},
			},
		];
		const { container } = render(<RiskRecentActivity entries={entries} />);
		expect(screen.getByText('moderate')).toBeInTheDocument();
		expect(container.textContent).toContain('50');
		expect(screen.getByText(/-2/)).toBeInTheDocument();
	});

	it('handles missing score_prev gracefully', () => {
		const entries: AuditEntry[] = [
			{
				sequence: 3,
				timestamp: '2026-05-09T10:00:00Z',
				actor: 'system',
				action: 'risk.recomputed',
				subject: 'host1',
				payload: {
					score: 45,
					level: 'moderate',
					trigger_reason: 'Initial assessment',
				},
			},
		];
		render(<RiskRecentActivity entries={entries} />);
		expect(screen.getByText(/moderate/)).toBeInTheDocument();
		expect(screen.getByText(/Initial assessment/)).toBeInTheDocument();
	});

	it('handles missing trigger_reason gracefully', () => {
		const entries: AuditEntry[] = [
			{
				sequence: 4,
				timestamp: '2026-05-09T10:00:00Z',
				actor: 'system',
				action: 'risk.recomputed',
				subject: 'host1',
				payload: {
					score: 50,
					level: 'moderate',
					score_prev: 50,
					level_prev: 'moderate',
				},
			},
		];
		render(<RiskRecentActivity entries={entries} />);
		expect(screen.getByText(/—/)).toBeInTheDocument();
	});

	it('displays relative time in title with full ISO', () => {
		const entries: AuditEntry[] = [
			{
				sequence: 5,
				timestamp: '2026-05-09T10:00:00Z',
				actor: 'system',
				action: 'risk.recomputed',
				subject: 'host1',
				payload: {
					score: 45,
					level: 'moderate',
					trigger_reason: 'Test',
				},
			},
		];
		const { container } = render(<RiskRecentActivity entries={entries} />);
		const timeSpan = container.querySelector('span[title]');
		expect(timeSpan).toBeTruthy();
	});
});
