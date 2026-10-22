/**
 * Vite Plugin for XAIO Design Mode
 *
 * Injects data-xaio-source attributes into JSX elements during development.
 * This enables precise source mapping for the design mode editor.
 *
 * Example transformation:
 *   Input:  <div className="container">
 *   Output: <div className="container" data-xaio-source="App.tsx:15:4">
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * ⚠️  CANONICAL COPY — MUST STAY BYTE-IDENTICAL IN TWO REPOSITORIES
 *
 * This exact file content is duplicated in:
 *   1. xaio-dev-server/src/xaio/templates/frontend/vite-plugin-xaio-design.ts
 *        → scaffolded into every NEW project at creation time.
 *   2. xaio-services/workspace-runner/src/templates/vite-plugin-xaio-design.ts
 *        → written into EVERY project (new and existing) on workspace boot by
 *          _ensure_vite_design_plugin(), overwriting whatever was there.
 *
 * Because the runner overwrites the file on every start/wake, a divergence here
 * silently defeats the other copy (that is how a stale version kept failing the
 * SonarCloud publish gate). When you edit one copy, edit the other in the SAME
 * change so they remain equal.
 *
 * KEEP THIS FILE DEPENDENCY-FREE (no magic-string or other npm deps): the runner
 * writes it into projects whose node_modules may predate those deps, and a
 * missing import crashes Vite. Only Node built-ins (node:fs, node:path) are safe.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { Plugin } from 'vite';
import { promises as fs } from 'node:fs';
import path from 'node:path';

interface XaioDesignPluginOptions {
  // Only inject in development mode (default: true)
  devOnly?: boolean;
  // File extensions to process
  extensions?: string[];
  // Exclude patterns (regex strings)
  exclude?: string[];
}

// Match < followed by a tag name, but not TypeScript generics.
const JSX_TAG_REGEX = /<([A-Z][a-zA-Z0-9]*|[a-z][a-zA-Z0-9-]*)\s*/g;

// True when `char` opens/closes a string literal (unescaped quote).
function isQuoteChar(char: string, prevChar: string): boolean {
  return (char === '"' || char === "'" || char === '`') && prevChar !== '\\';
}

// True when position `i` in `str` is the end of an opening tag (`>` or `/>`).
function isTagEndAt(str: string, i: number): boolean {
  const char = str[i];
  return char === '>' || (char === '/' && str[i + 1] === '>');
}

// Advance the in-string state when a quote is encountered.
function toggleString(
  inString: string | null,
  quote: string,
  inExpression: boolean
): string | null {
  if (inString === quote) return null;
  if (!inString && !inExpression) return quote;
  return inString;
}

// Precompute the byte offset at which each line starts.
function computeLineStarts(code: string): number[] {
  const lines = code.split('\n');
  const lineStarts: number[] = [0];
  for (let i = 0; i < lines.length; i++) {
    lineStarts.push(lineStarts[i] + lines[i].length + 1);
  }
  return lineStarts;
}

// Resolve a 1-based line/column for an absolute offset.
function getLineCol(
  lineStarts: number[],
  offset: number
): { line: number; col: number } {
  let line = 1;
  for (let i = 1; i < lineStarts.length; i++) {
    if (lineStarts[i] > offset) {
      line = i;
      break;
    }
  }
  const col = offset - lineStarts[line - 1] + 1;
  return { line, col };
}

// True when `pos` sits inside a string literal (e.g. a tag in an error message).
function isInsideString(code: string, pos: number): boolean {
  let inString: string | null = null;
  for (let i = 0; i < pos; i++) {
    const char = code[i];
    const prevChar = i > 0 ? code[i - 1] : '';
    if (!isQuoteChar(char, prevChar)) continue;
    if (inString === char) {
      inString = null;
    } else if (!inString) {
      inString = char;
    }
  }
  return inString !== null;
}

// True when a `<tag` match should be skipped: it is inside a string literal,
// or it looks like a TypeScript generic (preceded by a word char, `<`, `,`, `:`).
function isGenericOrStringContext(code: string, tagStart: number): boolean {
  if (isInsideString(code, tagStart)) return true;
  if (tagStart > 0 && /[\w<,:]/.test(code[tagStart - 1])) return true;
  return false;
}

// Offset (relative to `afterMatch`) of the opening tag's end, or -1 if none.
// Accounts for string literals, nested `{...}` JSX expressions, and TypeScript
// generic type arguments on the element (`<DataGrid<Article> .../>`) whose own
// `>` must NOT be mistaken for the opening tag's end.
function findTagEnd(afterMatch: string): number {
  let depth = 0;
  let angleDepth = 0;
  let inString: string | null = null;
  let inExpression = false;

  for (let i = 0; i < afterMatch.length; i++) {
    const char = afterMatch[i];
    const prevChar = i > 0 ? afterMatch[i - 1] : '';

    if (isQuoteChar(char, prevChar)) {
      inString = toggleString(inString, char, inExpression);
      continue;
    }
    if (inString) continue;

    if (char === '{') {
      depth++;
      inExpression = true;
    } else if (char === '}') {
      depth--;
      inExpression = depth !== 0;
    }
    if (inExpression) continue;

    // A generic type argument opens with `<` right after the component name
    // (e.g. `<DataGrid<Article>>`) and may nest (`<Table<Map<string, N>>>`).
    // Track its depth so the generic's closing `>` is consumed here and only
    // the real tag-terminating `>`/`/>` (at angleDepth 0) ends the tag. Without
    // this the attribute is spliced inside the generic list, producing invalid
    // TSX ("Expression expected" / "Expected ',', got 'ident'").
    if (char === '<') {
      angleDepth++;
      continue;
    }
    if (char === '>' && angleDepth > 0) {
      angleDepth--;
      continue;
    }

    if (angleDepth === 0 && isTagEndAt(afterMatch, i)) {
      return i;
    }
  }
  return -1;
}

// Scan `originalCode` for JSX opening tags and inject data-xaio-source.
// Dependency-free: collect insertions, then splice them in right-to-left so
// earlier offsets stay valid. Returns the transformed code, or null when
// nothing changed.
function injectSourceAttributes(originalCode: string, filename: string) {
  const lineStarts = computeLineStarts(originalCode);
  const insertions: Array<{ pos: number; attr: string }> = [];

  // Fresh regex per call so the shared `lastIndex` never leaks across files.
  const tagRegex = new RegExp(JSX_TAG_REGEX.source, 'g');

  let match: RegExpExecArray | null;
  while ((match = tagRegex.exec(originalCode)) !== null) {
    const tagStart = match.index;
    const tagName = match[1];
    if (!tagName) continue;
    if (isGenericOrStringContext(originalCode, tagStart)) continue;

    const afterMatch = originalCode.slice(match.index + match[0].length);
    const tagEndIndex = findTagEnd(afterMatch);
    if (tagEndIndex === -1) continue;

    // Skip if data-xaio-source already exists on this tag.
    const tagContent = afterMatch.slice(0, tagEndIndex);
    if (tagContent.includes('data-xaio-source')) continue;

    // Source location from ORIGINAL code.
    const { line, col } = getLineCol(lineStarts, tagStart);
    const insertPosition = match.index + match[0].length + tagEndIndex;
    insertions.push({
      pos: insertPosition,
      attr: ` data-xaio-source="${filename}:${line}:${col}"`,
    });
  }

  if (insertions.length === 0) return null;

  // Apply right-to-left so an earlier insertion never shifts a later offset.
  insertions.sort((a, b) => b.pos - a.pos);
  let result = originalCode;
  for (const { pos, attr } of insertions) {
    result = result.slice(0, pos) + attr + result.slice(pos);
  }
  return { code: result };
}

export default function xaioDesignPlugin(options: XaioDesignPluginOptions = {}): Plugin {
  const {
    devOnly = true,
    extensions = ['.tsx', '.jsx'],
    exclude = ['node_modules', '.test.', '.spec.', '__tests__']
  } = options;

  let isDev = true;  // Default to true for safety
  let previewConsoleLogPath: string | null = null;
  let lastClearAt = 0;

  return {
    name: 'vite-plugin-xaio-design',
    enforce: 'pre',  // Run before other plugins (like React) transform JSX

    configResolved(config) {
      // In cloud workspaces with bun vite, command might not be 'serve'
      // So we check for NOT being 'build' instead
      isDev = config.command !== 'build';
      // The browser-console log file sits at the project root (one level
      // above `frontend/`). Vite's `config.root` is the frontend dir.
      previewConsoleLogPath = path.resolve(config.root, '..', 'preview_console.jsonl');
      console.log(`[xaio-design] Plugin loaded, mode: ${config.command}, isDev: ${isDev}`);
    },

    // Clear the browser-console log file on every HMR update so that
    // `get_logs(preview)` never returns errors that the pending update
    // is about to fix. The file is cumulative across the session and
    // Vite HMR does not reset it on its own — without this, the agent
    // keeps seeing yesterday's stack trace after the fix lands.
    async handleHotUpdate(ctx) {
      if (!isDev || !previewConsoleLogPath) return;
      // Collapse bursts — Vite may fire `handleHotUpdate` per dependent
      // module. One clear per 100ms is plenty.
      const now = Date.now();
      if (now - lastClearAt < 100) return;
      lastClearAt = now;
      try {
        await fs.writeFile(previewConsoleLogPath, '');
      } catch (err: unknown) {
        const code = (err as NodeJS.ErrnoException)?.code;
        if (code !== 'ENOENT') {
          console.warn(`[xaio-design] Failed to clear preview console log: ${(err as Error).message}`);
        }
      }
      // Do not return anything — let Vite handle the update normally.
    },

    transform(code: string, id: string) {
      // Skip if not in dev mode and devOnly is true
      if (devOnly && !isDev) {
        console.log(`[xaio-design] Skipping ${id} - not in dev mode`);
        return null;
      }

      // Check file extension
      const hasValidExtension = extensions.some(ext => id.endsWith(ext));
      if (!hasValidExtension) {
        return null;
      }

      // Check exclusions
      const isExcluded = exclude.some(pattern => id.includes(pattern));
      if (isExcluded) {
        return null;
      }

      // Get relative path from src directory
      const srcIndex = id.indexOf('/src/');
      const filename = srcIndex === -1 ? (id.split('/').pop() || id) : id.slice(srcIndex + 5);

      // Use the code parameter provided by Vite (with enforce: 'pre', this is
      // the raw source). Do NOT use fs.readFileSync - it can return stale
      // content during HMR updates.
      try {
        const result = injectSourceAttributes(code, filename);
        if (!result) {
          console.log(`[xaio-design] No JSX tags found in ${filename}`);
          return null;
        }
        console.log(`[xaio-design] Transformed ${filename} - injected data-xaio-source attributes`);
        return result;
      } catch (error) {
        console.warn(`[xaio-design] Failed to process ${filename}:`, error);
        return null;
      }
    }
  };
}
