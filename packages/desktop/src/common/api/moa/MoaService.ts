/**
 * @license
 * Copyright 2025 AionUi (aionui.com)
 * SPDX-License-Identifier: Apache-2.0
 */

import { OpenAIRotatingClient } from '../OpenAIRotatingClient';
import type { MoaConfig, MoaModelConfig, MoaProposal, MoaResult } from './types';
import { DEFAULT_AGGREGATOR_PROMPT, DEFAULT_OPENROUTER_BASE_URL } from './types';

function buildProposerLabel(config: MoaModelConfig, index: number): string {
  return config.label ?? `Proposer ${index + 1}`;
}

function buildAggregatorMessages(userPrompt: string, proposals: MoaProposal[], aggregatorSystemPrompt: string) {
  const succeeded = proposals.filter((p) => !p.error);
  const proposalBlock = succeeded.map((p, i) => `--- Response ${i + 1} ---\n${p.content}`).join('\n\n');

  return [
    { role: 'system' as const, content: aggregatorSystemPrompt },
    {
      role: 'user' as const,
      content: `Original question:\n${userPrompt}\n\n${proposalBlock}\n\nSynthesize the best answer.`,
    },
  ];
}

export class MoaService {
  private readonly client: OpenAIRotatingClient;
  private readonly config: MoaConfig;

  constructor(config: MoaConfig) {
    this.config = config;
    this.client = new OpenAIRotatingClient(config.apiKey, {
      baseURL: config.baseUrl ?? DEFAULT_OPENROUTER_BASE_URL,
      timeout: config.timeout ?? 60_000,
      defaultHeaders: {
        'HTTP-Referer': 'https://aionui.com',
        'X-Title': 'AionUi MoA',
      },
    });
  }

  private async runProposer(
    model: MoaModelConfig,
    index: number,
    userPrompt: string,
    systemPrompt?: string
  ): Promise<MoaProposal> {
    const label = buildProposerLabel(model, index);
    const start = Date.now();

    const messages: Array<{ role: 'system' | 'user'; content: string }> = [];
    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }
    messages.push({ role: 'user', content: userPrompt });

    try {
      const response = await this.client.createChatCompletion({
        model: model.model,
        messages,
      });

      const content = response.choices[0]?.message?.content ?? '';

      return {
        model: model.model,
        label,
        content,
        latencyMs: Date.now() - start,
      };
    } catch (err) {
      return {
        model: model.model,
        label,
        content: '',
        latencyMs: Date.now() - start,
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  async run(userPrompt: string): Promise<MoaResult> {
    const totalStart = Date.now();

    const proposerPromises = this.config.proposers.map((model, i) =>
      this.runProposer(model, i, userPrompt, this.config.systemPrompt)
    );

    const proposals = await Promise.all(proposerPromises);

    const succeeded = proposals.filter((p) => !p.error);
    if (succeeded.length === 0) {
      return {
        finalContent: 'All proposer models failed. Check API key and model availability.',
        proposals,
        aggregatorModel: this.config.aggregator.model,
        totalLatencyMs: Date.now() - totalStart,
      };
    }

    if (succeeded.length === 1) {
      return {
        finalContent: succeeded[0].content,
        proposals,
        aggregatorModel: this.config.aggregator.model,
        totalLatencyMs: Date.now() - totalStart,
      };
    }

    const aggregatorPrompt = this.config.aggregatorPrompt ?? DEFAULT_AGGREGATOR_PROMPT;
    const aggregatorMessages = buildAggregatorMessages(userPrompt, proposals, aggregatorPrompt);

    try {
      const aggregatorResponse = await this.client.createChatCompletion({
        model: this.config.aggregator.model,
        messages: aggregatorMessages,
      });

      return {
        finalContent: aggregatorResponse.choices[0]?.message?.content ?? '',
        proposals,
        aggregatorModel: this.config.aggregator.model,
        totalLatencyMs: Date.now() - totalStart,
      };
    } catch (err) {
      const bestProposal = succeeded.reduce((a, b) => (a.content.length > b.content.length ? a : b));
      return {
        finalContent: `[Aggregator failed: ${err instanceof Error ? err.message : String(err)}]\n\nBest individual response:\n${bestProposal.content}`,
        proposals,
        aggregatorModel: this.config.aggregator.model,
        totalLatencyMs: Date.now() - totalStart,
      };
    }
  }
}
