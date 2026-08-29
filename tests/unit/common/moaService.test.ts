/**
 * @license
 * Copyright 2025 AionUi (aionui.com)
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MoaService } from '@/common/api/moa/MoaService';
import type { MoaConfig } from '@/common/api/moa/types';

let mockCreateChatCompletion: ReturnType<typeof vi.fn>;

vi.mock('@/common/api/OpenAIRotatingClient', () => {
  const MockClient = vi.fn();
  MockClient.prototype.createChatCompletion = vi.fn();
  return { OpenAIRotatingClient: MockClient };
});

function createConfig(overrides: Partial<MoaConfig> = {}): MoaConfig {
  return {
    proposers: [
      { model: 'model-a', label: 'Model A' },
      { model: 'model-b', label: 'Model B' },
      { model: 'model-c', label: 'Model C' },
    ],
    aggregator: { model: 'agg-model', label: 'Aggregator' },
    apiKey: 'test-key',
    ...overrides,
  };
}

function mockCompletion(content: string) {
  return {
    id: 'test',
    object: 'chat.completion',
    created: Date.now(),
    model: 'test',
    choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }],
  };
}

describe('MoaService', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { OpenAIRotatingClient } = await import('@/common/api/OpenAIRotatingClient');
    mockCreateChatCompletion = vi.fn();
    OpenAIRotatingClient.prototype.createChatCompletion = mockCreateChatCompletion;
  });

  it('fans out to all proposers and aggregates', async () => {
    mockCreateChatCompletion
      .mockResolvedValueOnce(mockCompletion('Response from A'))
      .mockResolvedValueOnce(mockCompletion('Response from B'))
      .mockResolvedValueOnce(mockCompletion('Response from C'))
      .mockResolvedValueOnce(mockCompletion('Synthesized answer'));

    const service = new MoaService(createConfig());
    const result = await service.run('What is 2+2?');

    expect(result.proposals).toHaveLength(3);
    expect(result.proposals[0].content).toBe('Response from A');
    expect(result.proposals[1].content).toBe('Response from B');
    expect(result.proposals[2].content).toBe('Response from C');
    expect(result.finalContent).toBe('Synthesized answer');
    expect(result.aggregatorModel).toBe('agg-model');
    expect(mockCreateChatCompletion).toHaveBeenCalledTimes(4);
  });

  it('returns single proposal when only one succeeds', async () => {
    mockCreateChatCompletion
      .mockRejectedValueOnce(new Error('rate limited'))
      .mockResolvedValueOnce(mockCompletion('Only survivor'))
      .mockRejectedValueOnce(new Error('timeout'));

    const service = new MoaService(createConfig());
    const result = await service.run('test');

    expect(result.finalContent).toBe('Only survivor');
    expect(result.proposals.filter((p) => p.error)).toHaveLength(2);
    expect(mockCreateChatCompletion).toHaveBeenCalledTimes(3);
  });

  it('returns error message when all proposers fail', async () => {
    mockCreateChatCompletion.mockRejectedValue(new Error('all down'));

    const service = new MoaService(createConfig());
    const result = await service.run('test');

    expect(result.finalContent).toContain('All proposer models failed');
    expect(result.proposals.every((p) => p.error)).toBe(true);
  });

  it('falls back to best proposal when aggregator fails', async () => {
    mockCreateChatCompletion
      .mockResolvedValueOnce(mockCompletion('Short'))
      .mockResolvedValueOnce(mockCompletion('This is a much longer and better response'))
      .mockResolvedValueOnce(mockCompletion('Medium length'))
      .mockRejectedValueOnce(new Error('aggregator down'));

    const service = new MoaService(createConfig());
    const result = await service.run('test');

    expect(result.finalContent).toContain('Aggregator failed');
    expect(result.finalContent).toContain('This is a much longer and better response');
  });

  it('uses custom aggregator prompt when provided', async () => {
    const customPrompt = 'Pick the funniest answer.';
    mockCreateChatCompletion
      .mockResolvedValueOnce(mockCompletion('A'))
      .mockResolvedValueOnce(mockCompletion('B'))
      .mockResolvedValueOnce(mockCompletion('C'))
      .mockResolvedValueOnce(mockCompletion('Final'));

    const service = new MoaService(createConfig({ aggregatorPrompt: customPrompt }));
    await service.run('test');

    const lastCall = mockCreateChatCompletion.mock.calls[3][0];
    expect(lastCall.messages[0].content).toBe(customPrompt);
  });

  it('records latency for each proposal', async () => {
    mockCreateChatCompletion
      .mockResolvedValueOnce(mockCompletion('A'))
      .mockResolvedValueOnce(mockCompletion('B'))
      .mockResolvedValueOnce(mockCompletion('C'))
      .mockResolvedValueOnce(mockCompletion('Final'));

    const service = new MoaService(createConfig());
    const result = await service.run('test');

    for (const p of result.proposals) {
      expect(p.latencyMs).toBeGreaterThanOrEqual(0);
    }
    expect(result.totalLatencyMs).toBeGreaterThanOrEqual(0);
  });

  it('uses default OpenRouter base URL', async () => {
    const { OpenAIRotatingClient } = await import('@/common/api/OpenAIRotatingClient');
    new MoaService(createConfig());
    expect(OpenAIRotatingClient).toHaveBeenCalledWith(
      'test-key',
      expect.objectContaining({ baseURL: 'https://openrouter.ai/api/v1' })
    );
  });

  it('assigns default labels when none provided', async () => {
    mockCreateChatCompletion.mockResolvedValueOnce(mockCompletion('A')).mockResolvedValueOnce(mockCompletion('Final'));

    const service = new MoaService(createConfig({ proposers: [{ model: 'unlabeled-model' }] }));
    const result = await service.run('test');

    expect(result.proposals[0].label).toBe('Proposer 1');
  });
});
