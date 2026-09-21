import type { EmbeddedSubtitleProbeResponse, EmbeddedSubtitleTrack } from "../types/embeddedSubtitles";

export const UNKNOWN_SUBTITLE_LANGUAGE = "und";

const UNKNOWN_LANGUAGE_VALUES = new Set(["und", "unknown", "auto"]);

/**
 * Keep the source language tag when it is usable by a WebVTT track. The API
 * uses a few common ISO 639-2 aliases (eng/zho/chi), which are also valid
 * language subtags and must retain their meaning.
 */
export function normalizeSubtitleLanguage(value: unknown): string {
  if (typeof value !== "string") return UNKNOWN_SUBTITLE_LANGUAGE;
  const language = value.trim();
  if (!language || UNKNOWN_LANGUAGE_VALUES.has(language.toLowerCase()) || !isBcp47LanguageTag(language)) {
    return UNKNOWN_SUBTITLE_LANGUAGE;
  }
  return language;
}

/** Find the language on the track selected by the probe response. */
export function subtitleLanguageForSelection(
  probe: EmbeddedSubtitleProbeResponse,
  selectedStreamIndex: number,
): string {
  const track = (probe.tracks ?? []).find((candidate) => candidate.streamIndex === selectedStreamIndex);
  return normalizeSubtitleLanguage((track as (EmbeddedSubtitleTrack & { language?: unknown }) | undefined)?.language);
}

/** Return the selected track so callers can reject stale or unavailable selections. */
export function subtitleTrackForSelection(
  probe: EmbeddedSubtitleProbeResponse,
  selectedStreamIndex: number | null,
): EmbeddedSubtitleTrack | undefined {
  if (selectedStreamIndex === null || !Number.isInteger(selectedStreamIndex)) return undefined;
  return (probe.tracks ?? []).find((track) => track.streamIndex === selectedStreamIndex);
}

export function isBcp47LanguageTag(value: string): boolean {
  if (!/^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$/.test(value)) return false;
  const parts = value.split("-");
  const language = parts.shift()!;
  if (!/^[A-Za-z]{2,8}$/.test(language)) return false;

  // Optional extlang subtags are three letters and occur only after a
  // two/three-letter primary language subtag.
  if (language.length <= 3) {
    while (parts.length && /^[A-Za-z]{3}$/.test(parts[0])) parts.shift();
  }
  if (parts.length && /^[A-Za-z]{4}$/.test(parts[0])) parts.shift(); // script
  if (parts.length && (/^[A-Za-z]{2}$/.test(parts[0]) || /^\d{3}$/.test(parts[0]))) parts.shift(); // region

  while (parts.length && /^(?:[A-Za-z0-9]{5,8}|\d[A-Za-z0-9]{3})$/.test(parts[0])) parts.shift();

  while (parts.length && /^[0-9A-WY-Za-wy-z]$/.test(parts[0])) {
    const singleton = parts.shift()!.toLowerCase();
    if (singleton === "x") {
      return parts.length > 0 && parts.every((part) => /^[A-Za-z0-9]{1,8}$/.test(part));
    }
    let extensionCount = 0;
    while (parts.length && /^[A-Za-z0-9]{2,8}$/.test(parts[0])) {
      parts.shift();
      extensionCount += 1;
    }
    if (extensionCount === 0) return false;
  }

  return parts.length === 0;
}
