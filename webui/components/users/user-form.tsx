'use client';

import { Checkbox } from '@/components/primitives/checkbox';
import { Input } from '@/components/primitives/input';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const userSchema = z.object({
	email: z.string().email(),
	displayName: z.string().optional(),
	kind: z.enum(['local', 'oidc']),
	disabled: z.boolean().optional(),
});

type UserFormData = z.infer<typeof userSchema>;

interface UserFormProps {
	initialData?: UserFormData;
	onSubmit: (data: UserFormData) => Promise<void>;
	isLoading?: boolean;
}

export function UserForm({ initialData, onSubmit, isLoading }: UserFormProps) {
	const {
		register,
		handleSubmit,
		formState: { errors },
	} = useForm<UserFormData>({
		resolver: zodResolver(userSchema),
		defaultValues: initialData,
	});

	return (
		<form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
			<Input
				label="Email"
				type="email"
				placeholder="user@example.com"
				required
				{...register('email')}
				error={errors.email?.message}
			/>
			<Input
				label="Display Name"
				placeholder="John Doe"
				{...register('displayName')}
				error={errors.displayName?.message}
			/>
			<div className="flex flex-col gap-2">
				<span className="text-small font-semibold text-text">User Kind</span>
				<div className="flex gap-4">
					<label className="flex items-center gap-2">
						<input type="radio" value="local" {...register('kind')} className="rounded" />
						<span className="text-small text-text">Local</span>
					</label>
					<label className="flex items-center gap-2">
						<input type="radio" value="oidc" {...register('kind')} className="rounded" />
						<span className="text-small text-text">OIDC</span>
					</label>
				</div>
			</div>
			<Checkbox label="Disabled" {...register('disabled')} />
			<button
				type="submit"
				disabled={isLoading}
				className="rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim disabled:opacity-50"
			>
				{isLoading ? 'Saving...' : 'Save User'}
			</button>
		</form>
	);
}
