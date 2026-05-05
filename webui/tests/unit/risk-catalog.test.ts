import { describe, it, expect } from 'vitest';
import { riskCatalog, type ActionType } from '@/lib/risk-catalog';

const REQUIRED: ActionType[] = [
  'reboot',
  'shell-exec',
  'pkg-update',
  'revoke-host',
  'delete-host',
  'mint-enrollment-token',
  'revoke-enrollment-token',
];

describe('riskCatalog', () => {
  it.each(REQUIRED)('has complete entry for %s', (action) => {
    const entry = riskCatalog[action];
    expect(entry).toBeDefined();
    expect(entry.displayName.length).toBeGreaterThan(0);
    expect(entry.summary.length).toBeGreaterThan(0);
    expect(entry.risks.length).toBeGreaterThan(0);
    expect(entry.rollback.length).toBeGreaterThan(0);
    expect(entry.technical.method).toMatch(/^(POST|DELETE|PUT|PATCH)$/);
    expect(entry.technical.pathTemplate.startsWith('/v1/')).toBe(true);
  });
});
