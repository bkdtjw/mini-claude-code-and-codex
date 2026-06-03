import type { Provider } from "@/types";

export const providerModels = (provider: Provider | null | undefined): string[] => {
  if (!provider) return [];
  return Array.from(new Set([...(provider.availableModels ?? []), provider.defaultModel].filter(Boolean)));
};

export const enabledProviders = (providers: Provider[]): Provider[] =>
  providers.filter((provider) => provider.enabled && providerModels(provider).length > 0);

export const supportsThinking = (provider: Provider | null | undefined, model: string): boolean => {
  if (!provider || !model) return false;
  const marker = `${provider.name} ${provider.baseUrl} ${model}`.toLowerCase();
  const isKimi = marker.includes("kimi") || marker.includes("moonshot");
  const modelName = model.toLowerCase();
  return isKimi && (modelName.includes("thinking") || modelName.includes("k2.5") || modelName.includes("k2.6"));
};
