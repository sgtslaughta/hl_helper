'use client';

import { OnboardingStep } from '@/components/onboarding/onboarding-step';
import { Button } from '@/components/primitives/button';
import { Select } from '@/components/primitives/select';
import { mintEnrollmentToken } from '@/lib/api/enrollment';
import { apiFetch } from '@/lib/api-client';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

const STEPS = [
	{ id: 'welcome', label: 'Welcome' },
	{ id: 'sso', label: 'Single Sign-On' },
	{ id: 'hosts', label: 'First Host' },
	{ id: 'notifications', label: 'Notifications' },
	{ id: 'security', label: 'Security Tour' },
];

export default function OnboardingPage() {
	const router = useRouter();
	const [currentStep, setCurrentStep] = useState(0);
	const [isLoading, setIsLoading] = useState(false);
	const [enrollmentCode, setEnrollmentCode] = useState('');
	const [ssoProvider, setSsoProvider] = useState('');
	const [notificationChannel, setNotificationChannel] = useState('');

	const handleFetchEnrollmentCode = async () => {
		setIsLoading(true);
		try {
			const data = await mintEnrollmentToken({ label: 'first-host', ttl_seconds: 900 });
			setEnrollmentCode(data.install_command);
		} catch (err) {
			console.error('Failed to mint enrollment token:', err);
			setEnrollmentCode('Error generating enrollment command');
		} finally {
			setIsLoading(false);
		}
	};

	const handleNotificationTest = async () => {
		setIsLoading(true);
		try {
			await apiFetch('/v1/notifications/test', {
				method: 'POST',
				body: JSON.stringify({ channel: notificationChannel }),
			});
		} catch (err) {
			console.error('Failed to send test notification:', err);
		} finally {
			setIsLoading(false);
		}
	};

	const handleFinish = async () => {
		setIsLoading(true);
		try {
			await apiFetch('/v1/users/me/prefs', {
				method: 'PATCH',
				body: JSON.stringify({ onboarding_complete: true }),
			});
			router.push('/');
		} catch (err) {
			console.error('Failed to complete onboarding:', err);
		} finally {
			setIsLoading(false);
		}
	};

	const handleNext = () => {
		if (currentStep < STEPS.length - 1) {
			setCurrentStep(currentStep + 1);
		} else {
			handleFinish();
		}
	};

	const handleBack = () => {
		if (currentStep > 0) {
			setCurrentStep(currentStep - 1);
		}
	};

	const handleSkip = () => {
		handleNext();
	};

	const renderStepContent = () => {
		switch (currentStep) {
			case 0: // Welcome
				return (
					<OnboardingStep step={1} headline="Welcome to HL Helper">
						<p className="text-base text-text-dim">
							Let's get you set up with a few essential configurations.
						</p>
					</OnboardingStep>
				);

			case 1: // SSO
				return (
					<OnboardingStep step={2} headline="Configure Single Sign-On">
						<p className="text-text-dim mb-4">Choose your SSO provider</p>
						<Select
							value={ssoProvider}
							onValueChange={setSsoProvider}
							options={[
								{ value: 'okta', label: 'Okta' },
								{ value: 'keycloak', label: 'Keycloak' },
								{ value: 'google', label: 'Google' },
								{ value: 'custom', label: 'Custom OIDC' },
							]}
						/>
					</OnboardingStep>
				);

			case 2: // Hosts
				return (
					<OnboardingStep step={3} headline="Add Your First Host">
						<p className="text-text-dim mb-4">
							Run this command on your first host to install the agent and register it.
							The token expires in 15 minutes.
						</p>
						{!enrollmentCode ? (
							<Button onClick={handleFetchEnrollmentCode} disabled={isLoading} type="button">
								{isLoading ? 'Generating...' : 'Generate install command'}
							</Button>
						) : (
							<div className="bg-surface-2 rounded p-4 font-mono text-sm text-text-dim overflow-auto whitespace-pre-wrap break-all">
								<code>{enrollmentCode}</code>
							</div>
						)}
					</OnboardingStep>
				);

			case 3: // Notifications
				return (
					<OnboardingStep step={4} headline="Configure Notifications">
						<p className="text-text-dim mb-4">Select your notification channel</p>
						<Select
							value={notificationChannel}
							onValueChange={setNotificationChannel}
							options={[
								{ value: 'email', label: 'Email' },
								{ value: 'slack', label: 'Slack' },
								{ value: 'discord', label: 'Discord' },
								{ value: 'webhook', label: 'Webhook' },
							]}
						/>
						{notificationChannel && (
							<Button
								onClick={handleNotificationTest}
								disabled={isLoading}
								type="button"
								className="mt-4"
							>
								{isLoading ? 'Sending...' : 'Send Test Notification'}
							</Button>
						)}
					</OnboardingStep>
				);

			case 4: // Security
				return (
					<OnboardingStep step={5} headline="Security Configuration Complete">
						<p className="text-text-dim">
							Visit the{' '}
							<a href="/security" className="text-accent hover:text-accent-dim">
								Security page
							</a>{' '}
							for additional configuration options.
						</p>
					</OnboardingStep>
				);

			default:
				return null;
		}
	};

	return (
		<div className="flex min-h-screen items-center justify-center bg-canvas p-8">
			<div className="w-full max-w-2xl">
				{renderStepContent()}

				{/* Footer Navigation */}
				<div className="flex gap-4 justify-between mt-12">
					<Button variant="ghost" onClick={handleBack} disabled={currentStep === 0} type="button">
						Back
					</Button>

					<Button variant="ghost" onClick={handleSkip} type="button">
						Skip
					</Button>

					<Button onClick={handleNext} disabled={isLoading} type="button">
						{currentStep === STEPS.length - 1 ? 'Finish' : 'Next'}
					</Button>
				</div>
			</div>
		</div>
	);
}
