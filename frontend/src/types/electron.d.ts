export {};

declare global {
  interface Window {
    electronAPI?: {
      selectFolder: () => Promise<string | null>;
      getCwd: () => Promise<string>;
      platform: string;
    };
  }
}
