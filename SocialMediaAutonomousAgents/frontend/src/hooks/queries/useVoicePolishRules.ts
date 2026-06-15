import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';

export type BannedPhrase = {
  pattern: string;
  replacement: string | null;
};

export type ContrastPattern = {
  name: string;
  description: string;
};

export type VoicePolishRules = {
  banned_phrases: BannedPhrase[];
  contrast_patterns: ContrastPattern[];
  punctuation_rules: string[];
  tone_rules: string[];
};

async function fetchVoicePolishRules(): Promise<VoicePolishRules> {
  return apiFetch<VoicePolishRules>('/voice-polish-rules');
}

export function useVoicePolishRules() {
  return useQuery<VoicePolishRules, Error>({
    queryKey: ['voicePolishRules'],
    queryFn: fetchVoicePolishRules,
  });
}
