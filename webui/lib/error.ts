/* RFC 9457 Problem Detail */
export interface ProblemDetail {
	type?: string;
	title: string;
	status: number;
	detail?: string;
	instance?: string;
	[key: string]: unknown; // extensible
}

export class ApiError extends Error {
	constructor(
		public status: number,
		public code: string,
		public detail: string,
		public problem?: ProblemDetail,
	) {
		super(detail);
		this.name = 'ApiError';
	}
}
