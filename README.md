# Compendium

One [MCP](https://modelcontextprotocol.io) server for all your personal knowledge: notes, documents, and data.

Point it at a Markdown vault, a folder of PDFs, a CSV, or all three, and an AI assistant can search across them, read what it finds, and cite where it came from. The server runs locally, makes no network calls of its own, and only reads unless you say otherwise. Content the assistant reads is passed to your AI client as usual, so point it only at data you are comfortable sharing with that provider.

> "What did I decide about hosting, and is there a book I noted about it?"
> The assistant searches `notes`, `docs`, and `books` in one call and cites `notes:projects/website.md` and `books:library.csv#4`.

## Sources

| Type | What it serves | Extras |
|---|---|---|
| `markdown` | A folder of `.md` notes (Obsidian-style vaults work) | tags, `[[wikilinks]]` / backlinks, optional additive writes |
| `files` | `.txt`, `.pdf`, `.docx` documents (always read-only) | PDF/DOCX need `pip install "compendium-mcp[pdf,docx]"` |
| `csv` | Every row of a CSV (or folder of CSVs) is an item | `title_column`, `delimiter` |

Adding another kind of source (a database, an issue tracker, an email archive) means implementing one small class. See [Adding a source](#adding-a-source).

## Tools

The tool set is small and the same whatever sources you configure. Results carry a `ref` like `source:id`.

| Tool | Purpose |
|---|---|
| `list_sources` | Configured sources, their types and capabilities |
| `search` | Ranked search across all sources (or one), with snippets |
| `list_items` | Browse by source, tag, or folder, newest first |
| `read_item` | Full content of an item by `ref` |
| `find_links` | Items that link to this one (only offered if a source supports links) |
| `create_item`, `append_to_item` | Additive writes (only offered if a source is writable) |

Items are also available as **resources** (`compendium://notes/projects/web.md`), and a `weekly_review` **prompt** guides the assistant through summarising recent changes.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/vfuoglio/compendium && cd compendium
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

Quick start on one folder (read-only; add `--writable` to allow `create_item` / `append_to_item`):

```bash
compendium --dir ~/notes
```

Or describe several sources in a `compendium.toml` ([full example](example/compendium.toml)):

```toml
[sources.notes]
type = "markdown"
path = "~/notes"
read_only = false      # sources are read-only unless you opt in

[sources.docs]
type = "files"
path = "~/Documents/reference"

[sources.books]
type = "csv"
path = "~/data/books.csv"
title_column = "title"
```

Config is found via `--config`, `$COMPENDIUM_CONFIG`, `./compendium.toml`, or `~/.config/compendium/config.toml`. Try the bundled example with the MCP inspector (with your venv activated so `compendium` is on the PATH):

```bash
npx @modelcontextprotocol/inspector compendium --config example/compendium.toml
```

### Claude Code

```bash
claude mcp add compendium -- /path/to/compendium/.venv/bin/compendium --config /path/to/compendium.toml
```

### Claude Desktop

```json
{
  "mcpServers": {
    "compendium": {
      "command": "/path/to/compendium/.venv/bin/compendium",
      "args": ["--config", "/path/to/compendium.toml"]
    }
  }
}
```

## Design decisions

- **Sources are plugins behind one interface.** `core.Source` defines `list`, `read`, and `search`; links and writes are optional capabilities a source opts into. A `Hub` merges sources and handles `source:id` references, so the tools never change as you add sources, and the model's tool list stays small.
- **Tools adapt to what's configured.** If nothing is writable, the write tools are not offered at all, rather than offered and refused. The server instructions list the actual sources and their access levels.
- **Read-only by default.** Writes need an explicit `read_only = false`, and even then they are additive: no delete, overwrite, or edit tool exists. Tools carry MCP annotations (`readOnlyHint`, `destructiveHint: false`) so clients can show accurate permission prompts.
- **Safe by construction.** File-backed sources resolve every path against their root and reject `..`, absolute paths, symlinks pointing outside, hidden folders (`.git`, `.obsidian`), and unexpected file types. Escaping symlinks are also hidden from listings and search. Each case has a test.
- **Errors the model can act on.** Expected failures (not found, read-only, unknown source) come back as tool errors with a clear message, so the assistant can correct itself. Unexpected crashes stay generic and never leak internals.
- **Strict config.** Typos in option names, bad source names, unknown types, and missing folders fail at startup with a specific message, not silently at query time.
- **No index to maintain.** Search scans sources on each call, with text and table caches keyed on modification time so PDFs and CSVs are parsed once. That is fast for personal-scale data and can never be stale.
- **One scoring function for every source.** Title and tag matches weigh more, and matching more of the query's terms beats repeating one term, so results from different sources can be ranked against each other.

## Adding a source

Subclass `Source`, implement three methods, and register it:

```python
# src/compendium_mcp/sources/mysource.py
from ..core import Hit, Item, Source, query_terms, score_text

class MySource(Source):
    type_name = "mysource"

    @classmethod
    def from_config(cls, name, cfg, base):
        return cls(name)

    def list(self, tag=None, folder=None) -> list[Item]: ...
    def read(self, item_id: str) -> str: ...
    def search(self, terms: list[str], limit: int) -> list[Hit]: ...
```

Add it to `SOURCE_TYPES` in `sources/__init__.py`, and `type = "mysource"` works in the config. Set `supports_links` / `supports_write` and override `links` / `create` / `append` to opt into those capabilities.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests cover each source, ranking, path safety, read-only enforcement, config validation, and a real MCP client talking to the server in-process (tool lists, annotations, error reporting, resources, prompt).

## Limitations

- Keyword search only, with no semantic ranking. Pair it with an embedding index (see [DocTalk](https://github.com/vfuoglio/doctalk)) for meaning-based search.
- Scans per query: fine for thousands of items, slow for hundreds of thousands.
- stdio transport only; a remote HTTP deployment would need authentication added first.

## License

MIT
