export default function AuthLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	return (
		<div className="flex h-screen w-screen">
			<div className="flex-1 flex items-center justify-center bg-canvas">{children}</div>
		</div>
	);
}
