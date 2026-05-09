import type { PillarOut } from '@/lib/api/posture-risk';
import type { ReactNode } from 'react';

export type PillarDetailRenderer = (p: PillarOut) => ReactNode;

/**
 * Plugin registry: maps a scorer's `name` to an optional custom detail
 * widget rendered below the standard pillar card body. Phase-1 ships
 * empty; future scorer plugins append entries here.
 */
export const PILLAR_DETAIL_RENDERERS: Record<string, PillarDetailRenderer> = {};
