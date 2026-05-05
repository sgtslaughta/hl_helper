import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface OnboardingState {
	currentStep: number;
	setCurrentStep: (step: number) => void;
	clear: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
	persist(
		set => ({
			currentStep: 0,
			setCurrentStep: (step: number) => set({ currentStep: step }),
			clear: () => set({ currentStep: 0 }),
		}),
		{
			name: 'onboarding-progress',
		},
	),
);
