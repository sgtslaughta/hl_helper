'use client';

export const dynamic = 'force-dynamic';

export default function ApiDocsPage() {
	return (
		<div className="flex flex-col gap-8 p-8">
			<div>
				<h1 className="text-2xl font-bold text-text">API Reference</h1>
				<p className="text-text-dim mt-2">REST API documentation</p>
			</div>

			<div className="rounded border border-hairline bg-surface p-6">
				<h2 className="text-lg font-semibold text-text mb-4">OpenAPI Specification</h2>
				<p className="text-small text-text-dim mb-4">
					Access the OpenAPI specification at the endpoint below. Scalar embed integration coming in
					Wave 3.
				</p>
				<div className="bg-surface-2 rounded p-4 font-mono text-sm text-text-dim mb-6">
					<code>curl https://api.example.com/api/openapi.json</code>
				</div>
				<p className="text-small text-text-dim">
					The OpenAPI specification contains complete API documentation, request/response schemas,
					and authentication details.
				</p>
			</div>
		</div>
	);
}
