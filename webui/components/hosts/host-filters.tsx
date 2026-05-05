'use client';

import { Button } from '@/components/primitives/button';
import { useState } from 'react';

interface HostFiltersProps {
	onStatusChange?: (status: string) => void;
	onSearch?: (query: string) => void;
}

const statuses = ['all', 'healthy', 'warning', 'critical'];

export function HostFilters({ onStatusChange, onSearch }: HostFiltersProps) {
	const [selectedStatus, setSelectedStatus] = useState('all');
	const [searchQuery, setSearchQuery] = useState('');

	const handleStatusChange = (status: string) => {
		setSelectedStatus(status);
		onStatusChange?.(status);
	};

	const handleSearchChange = (query: string) => {
		setSearchQuery(query);
		onSearch?.(query);
	};

	return (
		<div className="flex gap-4 mb-6 p-4 bg-surface rounded">
			<div className="flex-1">
				<input
					type="text"
					placeholder="Search hosts..."
					value={searchQuery}
					onChange={e => handleSearchChange(e.target.value)}
					className="w-full px-3 py-2 rounded bg-surface-2 border border-hairline text-text placeholder:text-text-dim focus:outline-none focus:border-accent"
				/>
			</div>
			<div className="flex gap-2">
				{statuses.map(status => (
					<Button
						key={status}
						variant={selectedStatus === status ? 'primary' : 'ghost'}
						size="sm"
						type="button"
						onClick={() => handleStatusChange(status)}
					>
						{status}
					</Button>
				))}
			</div>
		</div>
	);
}
