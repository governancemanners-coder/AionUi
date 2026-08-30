/**
 * @license
 * Copyright 2025 AionUi (aionui.com)
 * SPDX-License-Identifier: Apache-2.0
 */

export type MoaModelConfig = {
  model: string;
  label?: string;
};

export type MoaConfig = {
  proposers: MoaModelConfig[];
  aggregator: MoaModelConfig;
  apiKey: string;
  baseUrl?: string;
  systemPrompt?: string;
  aggregatorPrompt?: string;
  timeout?: number;
};

export type MoaProposal = {
  model: string;
  label: string;
  content: string;
  latencyMs: number;
  error?: string;
};

export type MoaResult = {
  finalContent: string;
  proposals: MoaProposal[];
  aggregatorModel: string;
  totalLatencyMs: number;
};

export const DEFAULT_OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1';

export const DEFAULT_PROPOSER_MODELS: MoaModelConfig[] = [
  { model: 'google/gemini-2.0-flash-exp:free', label: 'Gemini Flash' },
  { model: 'meta-llama/llama-3.1-8b-instruct:free', label: 'Llama 3.1' },
  { model: 'qwen/qwen3-8b:free', label: 'Qwen 3' },
];

export const DEFAULT_AGGREGATOR_MODEL: MoaModelConfig = {
  model: 'google/gemini-2.0-flash-exp:free',
  label: 'Aggregator',
};

export const DEFAULT_AGGREGATOR_PROMPT = `You are a response synthesizer. You have received multiple independent responses to the same user query from different AI assistants. Your job is to produce the single best answer by:

1. Identifying the strongest, most accurate parts from each response
2. Resolving any contradictions by favoring the most well-reasoned position
3. Combining complementary information into a coherent whole
4. Maintaining a clear, direct tone

Do NOT mention that multiple responses were consulted. Present your answer as a single, authoritative response.`;
